from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .dbc import DbcDecoder
from .logical_records import (
    LogicalMessageRecord,
    iter_logical_message_csv,
    logical_message_path_for_session,
    reinterpret_raw_record,
)
from .protocols import ProtocolRegistry
from .session_stream import SessionPagedReader, iter_session_frames
from .stream_pipeline import StreamingTransportPipeline

CACHE_FORMAT = "crt-logical-cache"
CACHE_VERSION = 1
DECODER_SIGNATURE = "transport-v2;protocol-v3;dbc-v2"
INSERT_BATCH_SIZE = 1_000

ProgressCallback = Callable[[int], None]
StatusCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class LogicalCacheInfo:
    path: Path
    total_messages: int
    source: str
    fingerprint: str
    decoder_signature: str
    dbc_signature: str
    created_at_utc: str
    reused: bool


def logical_cache_path_for_session(session_path: str | Path) -> Path:
    path = Path(session_path)
    suffix = ".crt.jsonl"
    if path.name.lower().endswith(suffix):
        return path.with_name(path.name[: -len(suffix)] + ".logical.sqlite")
    return path.with_suffix(path.suffix + ".logical.sqlite")


def ensure_logical_cache(
    session_path: str | Path,
    *,
    dbc_paths: Iterable[str | Path] = (),
    force: bool = False,
    progress: ProgressCallback | None = None,
    status: StatusCallback | None = None,
) -> LogicalCacheInfo:
    session = Path(session_path).resolve()
    active_dbc_paths = tuple(Path(item).resolve() for item in dbc_paths)
    cache_path = logical_cache_path_for_session(session)
    source_fingerprint, dbc_signature = _analysis_fingerprint(session, active_dbc_paths)

    if not force:
        cached = read_logical_cache_info(cache_path)
        if (
            cached is not None
            and cached.fingerprint == source_fingerprint
            and cached.decoder_signature == DECODER_SIGNATURE
            and cached.dbc_signature == dbc_signature
        ):
            _emit_status(status, f"Gotowy zapisany obraz analityczny: {cache_path.name}")
            _emit_progress(progress, 100)
            return LogicalCacheInfo(
                path=cached.path,
                total_messages=cached.total_messages,
                source=cached.source,
                fingerprint=cached.fingerprint,
                decoder_signature=cached.decoder_signature,
                dbc_signature=cached.dbc_signature,
                created_at_utc=cached.created_at_utc,
                reused=True,
            )

    return _build_logical_cache(
        session,
        cache_path,
        active_dbc_paths,
        source_fingerprint,
        dbc_signature,
        progress=progress,
        status=status,
    )


def read_logical_cache_info(path: str | Path) -> LogicalCacheInfo | None:
    cache_path = Path(path)
    if not cache_path.is_file():
        return None
    try:
        with sqlite3.connect(cache_path) as connection:
            rows = dict(connection.execute("SELECT key, value FROM metadata"))
            if rows.get("format") != CACHE_FORMAT:
                return None
            if int(rows.get("version", "0")) != CACHE_VERSION:
                return None
            total = int(rows.get("total_messages", "0"))
            actual = int(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
            if total != actual:
                return None
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return None
    return LogicalCacheInfo(
        path=cache_path,
        total_messages=total,
        source=rows.get("source", "unknown"),
        fingerprint=rows.get("fingerprint", ""),
        decoder_signature=rows.get("decoder_signature", ""),
        dbc_signature=rows.get("dbc_signature", ""),
        created_at_utc=rows.get("created_at_utc", ""),
        reused=False,
    )


def open_logical_cache_readonly(path: str | Path) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    connection = sqlite3.connect(
        f"file:{resolved.as_posix()}?mode=ro",
        uri=True,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def record_from_cache_row(row: sqlite3.Row) -> LogicalMessageRecord:
    fields_text = str(row["fields_json"] or "")
    frame_sequences_text = str(row["frame_sequences_json"] or "[]")
    return LogicalMessageRecord(
        sequence=int(row["sequence"]),
        first_timestamp_ns=int(row["first_timestamp_ns"]),
        last_timestamp_ns=int(row["last_timestamp_ns"]),
        protocol=str(row["protocol"]),
        transport=str(row["transport"]),
        name=str(row["name"] or ""),
        arbitration_id=(
            None if row["arbitration_id"] is None else int(row["arbitration_id"])
        ),
        is_extended_id=bool(row["is_extended_id"]),
        pgn=None if row["pgn"] is None else int(row["pgn"]),
        source_address=(
            None if row["source_address"] is None else int(row["source_address"])
        ),
        destination_address=(
            None
            if row["destination_address"] is None
            else int(row["destination_address"])
        ),
        complete=bool(row["complete"]),
        frame_sequences=tuple(int(value) for value in json.loads(frame_sequences_text)),
        payload=bytes(row["payload"] or b""),
        error=str(row["error"] or ""),
        confidence=float(row["confidence"]),
        fields=json.loads(fields_text) if fields_text else {},
    )


def _build_logical_cache(
    session: Path,
    cache_path: Path,
    dbc_paths: tuple[Path, ...],
    fingerprint: str,
    dbc_signature: str,
    *,
    progress: ProgressCallback | None,
    status: StatusCallback | None,
) -> LogicalCacheInfo:
    temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    message_path = logical_message_path_for_session(session)
    active_dbc = DbcDecoder(dbc_paths) if dbc_paths else None
    base_registry = ProtocolRegistry()
    source = "messages-csv+dbc" if active_dbc is not None else "messages-csv"

    try:
        with sqlite3.connect(temporary) as connection:
            connection.execute("PRAGMA journal_mode = OFF")
            connection.execute("PRAGMA synchronous = OFF")
            connection.execute("PRAGMA temp_store = MEMORY")
            _create_schema(connection)

            if message_path.is_file():
                _emit_status(status, f"Zliczanie rekordów w {message_path.name}…")
                _emit_progress(progress, 5)
                total_hint = _count_csv_records(message_path)
                _emit_progress(progress, 12)
                records = (
                    reinterpret_raw_record(
                        record,
                        base_registry=base_registry,
                        dbc_decoder=active_dbc,
                    )
                    for record in iter_logical_message_csv(message_path)
                )
                total = _insert_records(
                    connection,
                    records,
                    total_hint=total_hint,
                    progress=progress,
                    status=status,
                    progress_start=12,
                    progress_end=88,
                )
            else:
                source = "reconstructed+dbc" if dbc_paths else "reconstructed"
                reader = SessionPagedReader(session)
                frame_count = reader.frame_count
                _emit_status(status, "Rekonstrukcja transportu z surowych ramek…")
                _emit_progress(progress, 5)
                protocols = ProtocolRegistry(dbc_paths=dbc_paths)
                pipeline = StreamingTransportPipeline()
                total = _reconstruct_and_insert(
                    connection,
                    session,
                    frame_count,
                    pipeline,
                    protocols,
                    progress=progress,
                    status=status,
                )

            _emit_status(status, "Budowanie indeksów analitycznych…")
            _emit_progress(progress, 90)
            _create_indexes(connection)
            created_at = datetime.now(timezone.utc).isoformat()
            metadata = {
                "format": CACHE_FORMAT,
                "version": str(CACHE_VERSION),
                "total_messages": str(total),
                "source": source,
                "fingerprint": fingerprint,
                "decoder_signature": DECODER_SIGNATURE,
                "dbc_signature": dbc_signature,
                "created_at_utc": created_at,
                "session_path": str(session),
            }
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                metadata.items(),
            )
            connection.commit()
            connection.execute("PRAGMA optimize")

        _emit_progress(progress, 97)
        os.replace(temporary, cache_path)
        _emit_status(
            status,
            f"Zapisano obraz analityczny: {total:,} wiadomości".replace(",", " "),
        )
        _emit_progress(progress, 100)
        return LogicalCacheInfo(
            path=cache_path,
            total_messages=total,
            source=source,
            fingerprint=fingerprint,
            decoder_signature=DECODER_SIGNATURE,
            dbc_signature=dbc_signature,
            created_at_utc=created_at,
            reused=False,
        )
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            sequence INTEGER NOT NULL,
            first_timestamp_ns INTEGER NOT NULL,
            last_timestamp_ns INTEGER NOT NULL,
            protocol TEXT NOT NULL,
            transport TEXT NOT NULL,
            name TEXT NOT NULL,
            arbitration_id INTEGER,
            is_extended_id INTEGER NOT NULL,
            pgn INTEGER,
            source_address INTEGER,
            destination_address INTEGER,
            sender TEXT NOT NULL,
            identity_text TEXT NOT NULL,
            complete INTEGER NOT NULL,
            frame_sequences_json TEXT NOT NULL,
            payload BLOB NOT NULL,
            error TEXT NOT NULL,
            confidence REAL NOT NULL,
            fields_json TEXT NOT NULL
        );
        """
    )


def _create_indexes(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX idx_messages_time ON messages(first_timestamp_ns);
        CREATE INDEX idx_messages_protocol ON messages(protocol);
        CREATE INDEX idx_messages_sender ON messages(sender);
        CREATE INDEX idx_messages_can_id ON messages(arbitration_id);
        CREATE INDEX idx_messages_name ON messages(name);
        CREATE INDEX idx_messages_complete ON messages(complete);
        """
    )


def _count_csv_records(path: Path) -> int:
    with path.open("rb") as handle:
        count = sum(1 for line in handle if line.strip())
    return max(0, count - 1)


def _insert_records(
    connection: sqlite3.Connection,
    records: Iterable[LogicalMessageRecord],
    *,
    total_hint: int,
    progress: ProgressCallback | None,
    status: StatusCallback | None,
    progress_start: int,
    progress_end: int,
) -> int:
    batch: list[tuple[object, ...]] = []
    inserted = 0
    for record in records:
        inserted += 1
        batch.append(_record_row(inserted, record))
        if len(batch) >= INSERT_BATCH_SIZE:
            _flush_batch(connection, batch)
            batch.clear()
            _report_decode_progress(
                inserted,
                total_hint,
                progress_start,
                progress_end,
                progress,
                status,
            )
    if batch:
        _flush_batch(connection, batch)
    _report_decode_progress(
        inserted,
        total_hint,
        progress_start,
        progress_end,
        progress,
        status,
    )
    return inserted


def _reconstruct_and_insert(
    connection: sqlite3.Connection,
    session: Path,
    frame_count: int,
    pipeline: StreamingTransportPipeline,
    protocols: ProtocolRegistry,
    *,
    progress: ProgressCallback | None,
    status: StatusCallback | None,
) -> int:
    batch: list[tuple[object, ...]] = []
    inserted = 0
    processed_frames = 0
    for frame in iter_session_frames(session):
        processed_frames += 1
        for message in pipeline.feed(frame):
            inserted += 1
            batch.append(_record_row(inserted, LogicalMessageRecord.from_decoded(protocols.decode(message))))
        if len(batch) >= INSERT_BATCH_SIZE:
            _flush_batch(connection, batch)
            batch.clear()
        if processed_frames % 4_096 == 0:
            value = 8 + int(78 * processed_frames / max(1, frame_count))
            _emit_progress(progress, min(86, value))
            _emit_status(
                status,
                (
                    f"Rekonstrukcja: {processed_frames:,}/{frame_count:,} ramek, "
                    f"{inserted:,} wiadomości"
                ).replace(",", " "),
            )
    for message in pipeline.flush():
        inserted += 1
        batch.append(_record_row(inserted, LogicalMessageRecord.from_decoded(protocols.decode(message))))
    if batch:
        _flush_batch(connection, batch)
    _emit_progress(progress, 88)
    return inserted


def _flush_batch(connection: sqlite3.Connection, batch: list[tuple[object, ...]]) -> None:
    connection.executemany(
        """
        INSERT INTO messages(
            id, sequence, first_timestamp_ns, last_timestamp_ns, protocol, transport,
            name, arbitration_id, is_extended_id, pgn, source_address,
            destination_address, sender, identity_text, complete,
            frame_sequences_json, payload, error, confidence, fields_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )


def _record_row(identifier: int, record: LogicalMessageRecord) -> tuple[object, ...]:
    fields = dict(record.fields or {})
    sender = _sender_text(record, fields)
    can_text = ""
    if record.arbitration_id is not None:
        width = 8 if record.is_extended_id else 3
        can_text = f"0x{record.arbitration_id:0{width}X}"
    elif record.pgn is not None:
        can_text = f"PGN 0x{record.pgn:05X}"
    identity = f"{can_text} {record.name}".casefold()
    return (
        identifier,
        int(record.sequence),
        int(record.first_timestamp_ns),
        int(record.last_timestamp_ns),
        str(record.protocol),
        str(record.transport),
        str(record.name or ""),
        record.arbitration_id,
        int(bool(record.is_extended_id)),
        record.pgn,
        record.source_address,
        record.destination_address,
        sender,
        identity,
        int(bool(record.complete)),
        json.dumps(list(record.frame_sequences), separators=(",", ":")),
        sqlite3.Binary(record.payload),
        str(record.error or ""),
        float(record.confidence),
        json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def _sender_text(record: LogicalMessageRecord, fields: dict[str, object]) -> str:
    for key in ("sender_name", "source_name", "ecu_name", "node_name"):
        value = fields.get(key)
        if value not in (None, ""):
            return str(value)
    if record.source_address is not None:
        return f"0x{record.source_address:02X}"
    return "—"


def _report_decode_progress(
    current: int,
    total: int,
    start: int,
    end: int,
    progress: ProgressCallback | None,
    status: StatusCallback | None,
) -> None:
    ratio = current / max(1, total)
    _emit_progress(progress, start + int((end - start) * min(1.0, ratio)))
    _emit_status(
        status,
        f"Dekodowanie: {current:,}/{total:,} wiadomości".replace(",", " "),
    )


def _analysis_fingerprint(
    session: Path,
    dbc_paths: tuple[Path, ...],
) -> tuple[str, str]:
    message_path = logical_message_path_for_session(session)
    source_parts = [
        _file_signature(session),
        _file_signature(message_path) if message_path.is_file() else "messages:none",
        DECODER_SIGNATURE,
    ]
    dbc_parts = [_file_content_signature(path) for path in dbc_paths]
    dbc_signature = hashlib.sha256("|".join(dbc_parts).encode("utf-8")).hexdigest()
    source_parts.append(dbc_signature)
    fingerprint = hashlib.sha256("|".join(source_parts).encode("utf-8")).hexdigest()
    return fingerprint, dbc_signature


def _file_signature(path: Path) -> str:
    stat = path.stat()
    return f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"


def _file_content_signature(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{path.resolve()}:{digest.hexdigest()}"


def _emit_progress(callback: ProgressCallback | None, value: int) -> None:
    if callback is not None:
        callback(max(0, min(100, int(value))))


def _emit_status(callback: StatusCallback | None, text: str) -> None:
    if callback is not None:
        callback(text)
