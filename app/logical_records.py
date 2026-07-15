from __future__ import annotations

import csv
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from .dbc import DbcDecoder
from .message_models import DecodedMessage, TransportKind, TransportMessage
from .protocols import ProtocolRegistry
from .session_stream import iter_session_frames
from .stream_pipeline import StreamingTransportPipeline


@dataclass(frozen=True, slots=True)
class LogicalMessageRecord:
    sequence: int
    first_timestamp_ns: int
    last_timestamp_ns: int
    protocol: str
    transport: str
    name: str
    arbitration_id: int | None
    is_extended_id: bool
    pgn: int | None
    source_address: int | None
    destination_address: int | None
    complete: bool
    frame_sequences: tuple[int, ...]
    payload: bytes
    error: str = ""
    confidence: float = 1.0
    fields: dict[str, Any] | None = None

    @property
    def frame_count(self) -> int:
        return len(self.frame_sequences)

    @property
    def payload_hex(self) -> str:
        return " ".join(f"{byte:02X}" for byte in self.payload)

    @classmethod
    def from_decoded(cls, decoded: DecodedMessage) -> "LogicalMessageRecord":
        message = decoded.message
        return cls(
            sequence=message.sequence,
            first_timestamp_ns=message.first_timestamp_ns,
            last_timestamp_ns=message.last_timestamp_ns,
            protocol=decoded.protocol.value,
            transport=message.transport.value,
            name=decoded.name,
            arbitration_id=message.arbitration_id,
            is_extended_id=message.is_extended_id,
            pgn=message.pgn,
            source_address=message.source_address,
            destination_address=message.destination_address,
            complete=message.complete,
            frame_sequences=message.frame_sequences,
            payload=message.payload,
            error=message.error,
            confidence=decoded.confidence,
            fields=dict(decoded.fields),
        )


def logical_message_path_for_session(session_path: str | Path) -> Path:
    path = Path(session_path)
    suffix = ".crt.jsonl"
    if path.name.lower().endswith(suffix):
        return path.with_name(path.name[: -len(suffix)] + ".messages.csv")
    return path.with_suffix(path.suffix + ".messages.csv")


def iter_logical_message_csv(path: str | Path) -> Iterator[LogicalMessageRecord]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if reader.fieldnames is None:
            raise ValueError("logical message CSV does not contain a header")
        for line_number, row in enumerate(reader, start=2):
            try:
                yield _record_from_csv_row(row)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"invalid logical message row at line {line_number}: {exc}"
                ) from exc


def decode_record_with_dbc(
    record: LogicalMessageRecord,
    decoder: DbcDecoder | None,
) -> LogicalMessageRecord:
    """Apply a DBC overlay without changing the stored raw logical record."""

    if decoder is None or record.transport != TransportKind.RAW.value:
        return record
    if record.arbitration_id is None:
        return record
    message = TransportMessage(
        sequence=record.sequence,
        first_timestamp_ns=record.first_timestamp_ns,
        last_timestamp_ns=record.last_timestamp_ns,
        transport=TransportKind.RAW,
        payload=record.payload,
        frame_sequences=record.frame_sequences,
        arbitration_id=record.arbitration_id,
        is_extended_id=record.is_extended_id,
        source_address=record.source_address,
        destination_address=record.destination_address,
        pgn=record.pgn,
        complete=record.complete,
        error=record.error,
    )
    if not decoder.matches(message):
        return record
    return LogicalMessageRecord.from_decoded(decoder.decode(message))


def load_recent_logical_messages(
    session_path: str | Path,
    *,
    max_rows: int = 20_000,
    dbc_paths: Iterable[str | Path] = (),
) -> tuple[list[LogicalMessageRecord], int, str]:
    """Load a bounded recent logical-message window without retaining the full file.

    Existing ``*.messages.csv`` is preferred. Active DBC files are applied as a
    reversible presentation overlay. When the CSV is unavailable, messages are
    reconstructed from the raw CRT session in one streaming pass.
    """

    if max_rows <= 0:
        raise ValueError("max_rows must be greater than zero")

    active_dbc_paths = tuple(Path(path) for path in dbc_paths)
    dbc_decoder = DbcDecoder(active_dbc_paths) if active_dbc_paths else None
    session = Path(session_path)
    message_path = logical_message_path_for_session(session)
    retained: deque[LogicalMessageRecord] = deque(maxlen=max_rows)
    total = 0

    if message_path.is_file():
        for record in iter_logical_message_csv(message_path):
            retained.append(decode_record_with_dbc(record, dbc_decoder))
            total += 1
        source = "messages-csv+dbc" if dbc_decoder is not None else "messages-csv"
        return list(retained), total, source

    pipeline = StreamingTransportPipeline()
    protocols = ProtocolRegistry(dbc_paths=active_dbc_paths)
    for frame in iter_session_frames(session):
        for message in pipeline.feed(frame):
            retained.append(LogicalMessageRecord.from_decoded(protocols.decode(message)))
            total += 1
    for message in pipeline.flush():
        retained.append(LogicalMessageRecord.from_decoded(protocols.decode(message)))
        total += 1
    source = "reconstructed+dbc" if active_dbc_paths else "reconstructed"
    return list(retained), total, source


def _record_from_csv_row(row: dict[str, str | None]) -> LogicalMessageRecord:
    can_id_text = (row.get("can_id") or "").strip()
    type_text = (row.get("type") or "").strip().upper()
    pgn_text = (row.get("pgn") or "").strip()
    source_text = (row.get("source") or "").strip()
    destination_text = (row.get("destination") or "").strip()
    frame_sequences_text = (row.get("frame_sequences") or "").strip()
    fields_text = (row.get("fields_json") or "").strip()
    complete_text = (row.get("complete") or "").strip().lower()

    return LogicalMessageRecord(
        sequence=int((row.get("message_sequence") or "0").strip()),
        first_timestamp_ns=_milliseconds_to_ns(row.get("timestamp_ms")),
        last_timestamp_ns=_milliseconds_to_ns(row.get("end_timestamp_ms")),
        protocol=(row.get("protocol") or "unknown").strip().lower(),
        transport=(row.get("transport") or "raw").strip().lower(),
        name=(row.get("name") or "").strip(),
        arbitration_id=int(can_id_text, 16) if can_id_text else None,
        is_extended_id=type_text == "EXT",
        pgn=int(pgn_text, 16) if pgn_text else None,
        source_address=int(source_text, 16) if source_text else None,
        destination_address=int(destination_text, 16) if destination_text else None,
        complete=complete_text in {"yes", "true", "1", "complete"},
        frame_sequences=tuple(
            int(value.strip())
            for value in frame_sequences_text.split(",")
            if value.strip()
        ),
        payload=bytes.fromhex((row.get("payload") or "").strip()),
        error=(row.get("error") or "").strip(),
        confidence=float((row.get("confidence") or "1").strip()),
        fields=json.loads(fields_text) if fields_text else {},
    )


def _milliseconds_to_ns(value: str | None) -> int:
    text = (value or "0").strip().replace(",", ".")
    return max(0, int(round(float(text) * 1_000_000)))
