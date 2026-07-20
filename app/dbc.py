from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cantools

from .message_models import DecodedMessage, ProtocolKind, TransportKind, TransportMessage


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


def inspect_dbc(path: str | Path) -> DbcInspection:
    database = cantools.database.load_file(str(Path(path)), strict=False)
    messages = tuple(database.messages)
    return DbcInspection(
        message_count=len(messages),
        standard_message_count=sum(not message.is_extended_frame for message in messages),
        extended_message_count=sum(message.is_extended_frame for message in messages),
    )


class DbcDecoder:
    """Decode raw CAN frames using one or more active project DBC files.

    Exact frame-ID matches always have priority. For extended frames CRT also
    supports the common J1939 DBC convention where source or destination bytes
    are stored as FE/FF wildcards. PDU1 messages are matched by PF plus the
    destination-address rule, while PDU2 messages are matched by their complete
    PGN (PF + group extension). The first active DBC remains deterministic when
    several files describe the same message.
    """

    def __init__(self, paths: Iterable[str | Path]) -> None:
        self._exact_messages: dict[tuple[int, bool], tuple[str, Any]] = {}
        self._extended_candidates: list[tuple[str, Any]] = []
        self._loaded_files: list[str] = []

        for path_like in paths:
            path = Path(path_like)
            database = cantools.database.load_file(str(path), strict=False)
            self._loaded_files.append(path.name)
            for message in database.messages:
                is_extended = bool(message.is_extended_frame)
                frame_id = _normalize_frame_id(int(message.frame_id), is_extended)
                key = (frame_id, is_extended)
                entry = (path.name, message)
                self._exact_messages.setdefault(key, entry)
                if is_extended:
                    self._extended_candidates.append(entry)

    @property
    def loaded_files(self) -> tuple[str, ...]:
        return tuple(self._loaded_files)

    def matches(self, message: TransportMessage) -> bool:
        return self._find_message(message) is not None

    def decode(self, message: TransportMessage) -> DecodedMessage:
        match = self._find_message(message)
        if match is None:
            raise KeyError("DBC decoder does not contain a matching CAN message")

        source_name, dbc_message, match_mode, match_score = match
        fields: dict[str, Any] = {
            "dbc_file": source_name,
            "dbc_message": dbc_message.name,
            "dbc_match_mode": match_mode,
            "dbc_match_score": match_score,
            "frame_id": int(dbc_message.frame_id),
            "is_extended_frame": bool(dbc_message.is_extended_frame),
            "declared_length": int(dbc_message.length),
            "cycle_time_ms": dbc_message.cycle_time,
            "senders": list(dbc_message.senders),
        }
        try:
            decoded = dbc_message.decode(
                message.payload,
                decode_choices=True,
                scaling=True,
                allow_truncated=True,
                allow_excess=True,
            )
            fields["signals"] = {
                name: _json_value(value) for name, value in decoded.items()
            }
            fields["signal_units"] = {
                signal.name: signal.unit
                for signal in dbc_message.signals
                if signal.unit
            }
            name = f"DBC {dbc_message.name}"
            confidence = 1.0
        except Exception as exc:
            fields["decode_error"] = str(exc)
            fields["signals"] = {}
            name = f"DBC {dbc_message.name} (decode error)"
            confidence = 0.5

        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.DBC,
            name=name,
            fields=fields,
            confidence=confidence,
        )

    def _find_message(
        self,
        message: TransportMessage,
    ) -> tuple[str, Any, str, int] | None:
        if message.transport is not TransportKind.RAW or message.arbitration_id is None:
            return None

        arbitration_id = _normalize_frame_id(
            int(message.arbitration_id),
            bool(message.is_extended_id),
        )
        exact = self._exact_messages.get((arbitration_id, message.is_extended_id))
        if exact is not None:
            return exact[0], exact[1], "exact-id", 100

        if not message.is_extended_id:
            return None

        best: tuple[str, Any, str, int] | None = None
        best_score = -1
        for source_name, dbc_message in self._extended_candidates:
            score = _j1939_match_score(arbitration_id, int(dbc_message.frame_id))
            if score is None or score <= best_score:
                continue
            best = source_name, dbc_message, "j1939-address-aware", score
            best_score = score
        return best


def _normalize_frame_id(frame_id: int, is_extended: bool) -> int:
    return frame_id & (0x1FFFFFFF if is_extended else 0x7FF)


def _split_j1939_id(frame_id: int) -> tuple[int, int, int, int]:
    normalized = frame_id & 0x1FFFFFFF
    priority = (normalized >> 26) & 0x7
    pdu_format = (normalized >> 16) & 0xFF
    pdu_specific = (normalized >> 8) & 0xFF
    source_address = normalized & 0xFF
    return priority, pdu_format, pdu_specific, source_address


def _j1939_match_score(received_id: int, dbc_id: int) -> int | None:
    rx_priority, rx_pf, rx_ps, rx_sa = _split_j1939_id(received_id)
    dbc_priority, dbc_pf, dbc_ps, dbc_sa = _split_j1939_id(dbc_id)

    if dbc_pf != rx_pf:
        return None

    score = 0
    if dbc_priority == rx_priority:
        score += 2

    if rx_pf < 240:
        # PDU1: PF identifies the PGN; PS is the destination address.
        if dbc_ps == rx_ps:
            score += 8
        elif dbc_ps in (0xFE, 0xFF):
            score += 2
        else:
            return None
    else:
        # PDU2: PS is the group extension and therefore part of the PGN.
        if dbc_ps != rx_ps:
            return None
        score += 8

    if dbc_sa == rx_sa:
        score += 6
    elif dbc_sa in (0xFE, 0xFF):
        score += 2
    else:
        return None

    return score


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)
