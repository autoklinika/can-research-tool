from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .message_models import DecodedMessage
from .models import CanFrame


class FrameCsvStreamWriter:
    """Append raw CAN frames to CSV without retaining them in memory."""

    def __init__(self, path: str | Path, *, flush_every: int = 256) -> None:
        if flush_every <= 0:
            raise ValueError("flush_every must be greater than zero")
        self.path = Path(path)
        self.flush_every = flush_every
        self._handle = None
        self._writer = None
        self._count = 0

    def open(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8-sig", newline="")
        self._writer = csv.writer(self._handle, delimiter=";")
        self._writer.writerow(
            [
                "timestamp_ms",
                "sequence",
                "can_id",
                "type",
                "dlc",
                "data",
                "channel",
                "remote",
                "error",
                "source_timestamp",
                "source_flags",
            ]
        )
        self._handle.flush()

    def append(self, frame: CanFrame) -> None:
        if self._writer is None or self._handle is None:
            raise RuntimeError("frame CSV writer is not open")
        id_width = 8 if frame.is_extended_id else 3
        self._writer.writerow(
            [
                f"{frame.timestamp_ns / 1_000_000:.6f}",
                frame.sequence,
                f"{frame.arbitration_id:0{id_width}X}",
                "EXT" if frame.is_extended_id else "STD",
                frame.dlc,
                frame.data_hex,
                frame.channel,
                "yes" if frame.is_remote_frame else "no",
                "yes" if frame.is_error_frame else "no",
                "" if frame.source_timestamp is None else frame.source_timestamp,
                frame.source_flags,
            ]
        )
        self._count += 1
        if self._count % self.flush_every == 0:
            self._handle.flush()

    def close(self) -> None:
        handle = self._handle
        self._handle = None
        self._writer = None
        if handle is not None:
            handle.flush()
            handle.close()

    def __enter__(self) -> "FrameCsvStreamWriter":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


class MessageCsvStreamWriter:
    """Append decoded logical messages as transport sessions complete."""

    def __init__(self, path: str | Path, *, flush_every: int = 64) -> None:
        if flush_every <= 0:
            raise ValueError("flush_every must be greater than zero")
        self.path = Path(path)
        self.flush_every = flush_every
        self._handle = None
        self._writer = None
        self._count = 0

    def open(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8-sig", newline="")
        self._writer = csv.writer(self._handle, delimiter=";")
        self._writer.writerow(
            [
                "timestamp_ms",
                "end_timestamp_ms",
                "message_sequence",
                "protocol",
                "transport",
                "name",
                "can_id",
                "type",
                "pgn",
                "source",
                "destination",
                "complete",
                "frame_count",
                "frame_sequences",
                "payload_length",
                "payload",
                "error",
                "confidence",
                "fields_json",
            ]
        )
        self._handle.flush()

    def append(self, decoded: DecodedMessage) -> None:
        if self._writer is None or self._handle is None:
            raise RuntimeError("message CSV writer is not open")
        message = decoded.message
        self._writer.writerow(
            [
                f"{message.first_timestamp_ns / 1_000_000:.6f}",
                f"{message.last_timestamp_ns / 1_000_000:.6f}",
                message.sequence,
                decoded.protocol.value,
                message.transport.value,
                decoded.name,
                _format_can_id(message.arbitration_id, message.is_extended_id),
                "EXT" if message.is_extended_id else "STD",
                "" if message.pgn is None else f"{message.pgn:05X}",
                _format_hex_byte(message.source_address),
                _format_hex_byte(message.destination_address),
                "yes" if message.complete else "no",
                message.frame_count,
                ",".join(str(value) for value in message.frame_sequences),
                len(message.payload),
                message.payload_hex,
                message.error,
                f"{decoded.confidence:.3f}",
                json.dumps(decoded.fields, ensure_ascii=False, separators=(",", ":")),
            ]
        )
        self._count += 1
        if self._count % self.flush_every == 0:
            self._handle.flush()

    def close(self) -> None:
        handle = self._handle
        self._handle = None
        self._writer = None
        if handle is not None:
            handle.flush()
            handle.close()

    def __enter__(self) -> "MessageCsvStreamWriter":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def _format_can_id(value: int | None, is_extended: bool) -> str:
    if value is None:
        return ""
    width = 8 if is_extended else 3
    return f"{value:0{width}X}"


def _format_hex_byte(value: int | None) -> str:
    return "" if value is None else f"{value:02X}"
