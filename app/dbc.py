from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cantools

from .message_models import DecodedMessage, ProtocolKind, TransportKind, TransportMessage

_MATCH_CACHE_LIMIT = 65_536
_PAYLOAD_CACHE_LIMIT = 4_096


@dataclass(frozen=True, slots=True)
class DbcFileRecord:
    id: str
    name: str
    relative_path: str
    enabled: bool
    message_count: int
    sha256: str
    added_at_utc: str


@dataclass(frozen=True, slots=True)
class DbcInspection:
    message_count: int
    standard_message_count: int
    extended_message_count: int


@dataclass(frozen=True, slots=True)
class _DbcMessageEntry:
    source_name: str
    message: Any
    priority: int
    pdu_format: int
    pdu_specific: int
    source_address: int
    senders: tuple[str, ...]
    signal_units: tuple[tuple[str, str], ...]


_DbcMatch = tuple[_DbcMessageEntry, str, int]
_PayloadResult = tuple[tuple[tuple[str, Any], ...], str]


def inspect_dbc(path: str | Path) -> DbcInspection:
    database = cantools.database.load_file(str(Path(path)), strict=False)
    messages = tuple(database.messages)
    return DbcInspection(
        message_count=len(messages),
        standard_message_count=sum(not message.is_extended_frame for message in messages),
        extended_message_count=sum(message.is_extended_frame for message in messages),
    )


class DbcDecoder:
    """Decode raw CAN frames using indexed, deterministic DBC matching.

    Exact frame-ID matches remain O(1). Extended J1939-style wildcard matches are
    pre-indexed by PF for PDU1 and by PF/group-extension for PDU2, so a received ID
    is never compared with every extended message in every active DBC. Match results
    are cached per CAN ID and decoded payloads use a small bounded LRU cache. This is
    especially important when hundreds of thousands of periodic frames reuse a small
    set of identifiers and payload values.
    """

    def __init__(self, paths: Iterable[str | Path]) -> None:
        self._exact_messages: dict[tuple[int, bool], _DbcMessageEntry] = {}
        self._pdu1_candidates: dict[int, list[_DbcMessageEntry]] = {}
        self._pdu2_candidates: dict[tuple[int, int], list[_DbcMessageEntry]] = {}
        self._loaded_files: list[str] = []
        self._match_cache: dict[tuple[int, bool], _DbcMatch | None] = {}
        self._payload_cache: OrderedDict[tuple[int, bytes], _PayloadResult] = OrderedDict()
        self._match_cache_hits = 0
        self._match_cache_misses = 0
        self._payload_cache_hits = 0
        self._payload_cache_misses = 0
        self._last_candidate_count = 0

        for path_like in paths:
            path = Path(path_like)
            database = cantools.database.load_file(str(path), strict=False)
            self._loaded_files.append(path.name)
            for message in database.messages:
                is_extended = bool(message.is_extended_frame)
                frame_id = _normalize_frame_id(int(message.frame_id), is_extended)
                priority, pdu_format, pdu_specific, source_address = _split_j1939_id(
                    frame_id
                )
                entry = _DbcMessageEntry(
                    source_name=path.name,
                    message=message,
                    priority=priority,
                    pdu_format=pdu_format,
                    pdu_specific=pdu_specific,
                    source_address=source_address,
                    senders=tuple(str(sender) for sender in message.senders),
                    signal_units=tuple(
                        (str(signal.name), str(signal.unit))
                        for signal in message.signals
                        if signal.unit
                    ),
                )
                self._exact_messages.setdefault((frame_id, is_extended), entry)
                if not is_extended:
                    continue
                if pdu_format < 240:
                    self._pdu1_candidates.setdefault(pdu_format, []).append(entry)
                else:
                    self._pdu2_candidates.setdefault(
                        (pdu_format, pdu_specific), []
                    ).append(entry)

    @property
    def loaded_files(self) -> tuple[str, ...]:
        return tuple(self._loaded_files)

    @property
    def cache_stats(self) -> dict[str, int]:
        """Return lightweight diagnostics used by performance regression tests."""

        return {
            "match_cache_entries": len(self._match_cache),
            "match_cache_hits": self._match_cache_hits,
            "match_cache_misses": self._match_cache_misses,
            "payload_cache_entries": len(self._payload_cache),
            "payload_cache_hits": self._payload_cache_hits,
            "payload_cache_misses": self._payload_cache_misses,
            "last_candidate_count": self._last_candidate_count,
        }

    def matches(self, message: TransportMessage) -> bool:
        return self._find_message(message) is not None

    def decode_if_matches(self, message: TransportMessage) -> DecodedMessage | None:
        """Decode once when matched, avoiding a separate matches/decode lookup pair."""

        match = self._find_message(message)
        if match is None:
            return None
        return self._decode_match(message, match)

    def decode(self, message: TransportMessage) -> DecodedMessage:
        decoded = self.decode_if_matches(message)
        if decoded is None:
            raise KeyError("DBC decoder does not contain a matching CAN message")
        return decoded

    def _decode_match(
        self,
        message: TransportMessage,
        match: _DbcMatch,
    ) -> DecodedMessage:
        entry, match_mode, match_score = match
        dbc_message = entry.message
        fields: dict[str, Any] = {
            "dbc_file": entry.source_name,
            "dbc_message": dbc_message.name,
            "dbc_match_mode": match_mode,
            "dbc_match_score": match_score,
            "frame_id": int(dbc_message.frame_id),
            "is_extended_frame": bool(dbc_message.is_extended_frame),
            "declared_length": int(dbc_message.length),
            "cycle_time_ms": dbc_message.cycle_time,
            "senders": list(entry.senders),
            "sender_name": ", ".join(entry.senders),
        }
        signals, decode_error = self._decode_payload(entry, message.payload)
        fields["signals"] = signals
        fields["signal_units"] = dict(entry.signal_units)
        if decode_error:
            fields["decode_error"] = decode_error
            name = f"DBC {dbc_message.name} (decode error)"
            confidence = 0.5
        else:
            name = f"DBC {dbc_message.name}"
            confidence = 1.0
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.DBC,
            name=name,
            fields=fields,
            confidence=confidence,
        )

    def _decode_payload(
        self,
        entry: _DbcMessageEntry,
        payload: bytes,
    ) -> tuple[dict[str, Any], str]:
        key = (id(entry.message), bytes(payload))
        cached = self._payload_cache.get(key)
        if cached is not None:
            self._payload_cache_hits += 1
            self._payload_cache.move_to_end(key)
            signal_items, decode_error = cached
            return dict(signal_items), decode_error

        self._payload_cache_misses += 1
        try:
            decoded = entry.message.decode(
                payload,
                decode_choices=True,
                scaling=True,
                allow_truncated=True,
                allow_excess=True,
            )
            signal_items = tuple(
                (str(name), _json_value(value)) for name, value in decoded.items()
            )
            decode_error = ""
        except Exception as exc:
            signal_items = ()
            decode_error = str(exc)

        self._payload_cache[key] = (signal_items, decode_error)
        self._payload_cache.move_to_end(key)
        while len(self._payload_cache) > _PAYLOAD_CACHE_LIMIT:
            self._payload_cache.popitem(last=False)
        return dict(signal_items), decode_error

    def _find_message(self, message: TransportMessage) -> _DbcMatch | None:
        if message.transport is not TransportKind.RAW or message.arbitration_id is None:
            return None

        arbitration_id = _normalize_frame_id(
            int(message.arbitration_id),
            bool(message.is_extended_id),
        )
        cache_key = (arbitration_id, bool(message.is_extended_id))
        if cache_key in self._match_cache:
            self._match_cache_hits += 1
            return self._match_cache[cache_key]

        self._match_cache_misses += 1
        exact = self._exact_messages.get(cache_key)
        if exact is not None:
            result: _DbcMatch | None = (exact, "exact-id", 100)
            self._last_candidate_count = 0
            self._remember_match(cache_key, result)
            return result
        if not message.is_extended_id:
            self._last_candidate_count = 0
            self._remember_match(cache_key, None)
            return None

        rx_priority, rx_pf, rx_ps, rx_sa = _split_j1939_id(arbitration_id)
        if rx_pf < 240:
            candidates = self._pdu1_candidates.get(rx_pf, ())
        else:
            candidates = self._pdu2_candidates.get((rx_pf, rx_ps), ())
        self._last_candidate_count = len(candidates)

        best: _DbcMatch | None = None
        best_score = -1
        for entry in candidates:
            score = _j1939_match_score_parts(
                rx_priority,
                rx_pf,
                rx_ps,
                rx_sa,
                entry,
            )
            if score is None or score <= best_score:
                continue
            best = (entry, "j1939-address-aware", score)
            best_score = score

        self._remember_match(cache_key, best)
        return best

    def _remember_match(
        self,
        key: tuple[int, bool],
        result: _DbcMatch | None,
    ) -> None:
        if len(self._match_cache) < _MATCH_CACHE_LIMIT:
            self._match_cache[key] = result


def _normalize_frame_id(frame_id: int, is_extended: bool) -> int:
    return frame_id & (0x1FFFFFFF if is_extended else 0x7FF)


def _split_j1939_id(frame_id: int) -> tuple[int, int, int, int]:
    normalized = frame_id & 0x1FFFFFFF
    priority = (normalized >> 26) & 0x7
    pdu_format = (normalized >> 16) & 0xFF
    pdu_specific = (normalized >> 8) & 0xFF
    source_address = normalized & 0xFF
    return priority, pdu_format, pdu_specific, source_address


def _j1939_match_score_parts(
    rx_priority: int,
    rx_pf: int,
    rx_ps: int,
    rx_sa: int,
    entry: _DbcMessageEntry,
) -> int | None:
    if entry.pdu_format != rx_pf:
        return None
    score = 2 if entry.priority == rx_priority else 0
    if rx_pf < 240:
        if entry.pdu_specific == rx_ps:
            score += 8
        elif entry.pdu_specific in (0xFE, 0xFF):
            score += 2
        else:
            return None
    else:
        if entry.pdu_specific != rx_ps:
            return None
        score += 8
    if entry.source_address == rx_sa:
        score += 6
    elif entry.source_address in (0xFE, 0xFF):
        score += 2
    else:
        return None
    return score


def _j1939_match_score(received_id: int, dbc_id: int) -> int | None:
    """Compatibility helper retained for direct unit tests and diagnostics."""

    rx_priority, rx_pf, rx_ps, rx_sa = _split_j1939_id(received_id)
    dbc_priority, dbc_pf, dbc_ps, dbc_sa = _split_j1939_id(dbc_id)
    entry = _DbcMessageEntry(
        source_name="",
        message=None,
        priority=dbc_priority,
        pdu_format=dbc_pf,
        pdu_specific=dbc_ps,
        source_address=dbc_sa,
        senders=(),
        signal_units=(),
    )
    return _j1939_match_score_parts(rx_priority, rx_pf, rx_ps, rx_sa, entry)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)
