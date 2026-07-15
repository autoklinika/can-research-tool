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

    DBC interpretation is deliberately layered above the raw transport model. A
    matching DBC never changes or discards the original CAN payload.
    """

    def __init__(self, paths: Iterable[str | Path]) -> None:
        self._messages: dict[tuple[int, bool], tuple[str, Any]] = {}
        self._loaded_files: list[str] = []
        for path_like in paths:
            path = Path(path_like)
            database = cantools.database.load_file(str(path), strict=False)
            self._loaded_files.append(path.name)
            for message in database.messages:
                key = (int(message.frame_id), bool(message.is_extended_frame))
                # The first enabled DBC has deterministic priority when files
                # contain the same frame identifier.
                self._messages.setdefault(key, (path.name, message))

    @property
    def loaded_files(self) -> tuple[str, ...]:
        return tuple(self._loaded_files)

    def matches(self, message: TransportMessage) -> bool:
        if message.transport is not TransportKind.RAW or message.arbitration_id is None:
            return False
        return (message.arbitration_id, message.is_extended_id) in self._messages

    def decode(self, message: TransportMessage) -> DecodedMessage:
        assert message.arbitration_id is not None
        source_name, dbc_message = self._messages[
            (message.arbitration_id, message.is_extended_id)
        ]
        fields: dict[str, Any] = {
            "dbc_file": source_name,
            "dbc_message": dbc_message.name,
            "frame_id": int(dbc_message.frame_id),
            "is_extended_frame": bool(dbc_message.is_extended_frame),
            "declared_length": int(dbc_message.length),
            "cycle_time_ms": dbc_message.cycle_time,
            "senders": list(dbc_message.senders),
        }
        try:
            decoded = dbc_message.decode_simple(
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


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)
