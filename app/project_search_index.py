from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

from . import sqlite_connection as sqlite3
from .project import CrtProject, SessionRecord
from .search_engine import (
    CompiledSearchQuery,
    SearchDocument,
    SearchEngine,
    SearchHit,
    SearchLogic,
    SearchMode,
    SearchQuery,
)
from .session_stream import SessionPagedReader


SEARCH_INDEX_SCHEMA_VERSION = 1
SEARCH_SOURCE_KIND = "raw-can-frames"
SEARCH_HEADERS = (
    "Czas [ms]",
    "Sekwencja",
    "CAN ID",
    "Typ",
    "DLC",
    "Dane",
    "Kanał",
    "Flagi",
)

_FIELD_COLUMNS: dict[str, tuple[str, str]] = {
    "Czas [ms]": ("timestamp_text", "timestamp_norm"),
    "Sekwencja": ("sequence_text", "sequence_norm"),
    "CAN ID": ("can_id_text", "can_id_norm"),
    "Typ": ("type_text", "type_norm"),
    "DLC": ("dlc_text", "dlc_norm"),
    "Dane": ("data_text", "data_norm"),
    "Kanał": ("channel_text", "channel_norm"),
    "Flagi": ("flags_text", "flags_norm"),
}
_RAW_SELECT_COLUMNS = tuple(value[0] for value in _FIELD_COLUMNS.values())


@dataclass(frozen=True, slots=True)
class SessionSearchFingerprint:
    source_id: str
    session_id: str
    relative_path: str
    sha256: str
    file_size: int
    mtime_ns: int
    frame_count: int
    schema_version: int = SEARCH_INDEX_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class SearchIndexState:
    status: str
    indexed_rows: int
    total_rows: int
    error: str = ""


class ProjectSearchIndex:
    """Persistent, rebuildable search cache stored inside one CRT project."""

    def __init__(self, project: CrtProject | str | Path) -> None:
        root = Path(project.root if isinstance(project, CrtProject) else project).resolve()
        self.project_root = root
        self.path = root / ".crt" / "indexes" / "search-v1.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def source_id_for(session_id: str) -> str:
        return f"session:{session_id}:raw:v{SEARCH_INDEX_SCHEMA_VERSION}"

    def fingerprint(
        self,
        project: CrtProject,
        session: SessionRecord,
        session_path: str | Path | None = None,
    ) -> SessionSearchFingerprint:
        path = (
            Path(session_path).resolve()
            if session_path is not None
            else project.absolute_path(session.relative_path)
        )
        stat = path.stat()
        return SessionSearchFingerprint(
            source_id=self.source_id_for(session.id),
            session_id=session.id,
            relative_path=project.relative_path(path),
            sha256=session.sha256,
            file_size=int(stat.st_size),
            mtime_ns=int(stat.st_mtime_ns),
            frame_count=int(session.frame_count),
        )

    def state(self, source_id: str) -> SearchIndexState | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, indexed_rows, frame_count, error FROM sources WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            return None
        return SearchIndexState(
            status=str(row[0]),
            indexed_rows=int(row[1]),
            total_rows=int(row[2]),
            error=str(row[3] or ""),
        )

    def is_current(self, fingerprint: SessionSearchFingerprint) -> bool:
        """Return whether a complete durable index matches the session content.

        A timestamp-only change does not invalidate the cache. When ``mtime``
        differs, the source file is verified against the project-owned SHA-256
        before the stored metadata is refreshed.
        """

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, relative_path, schema_version, sha256,
                       file_size, mtime_ns, frame_count, indexed_rows, status
                FROM sources WHERE source_id = ?
                """,
                (fingerprint.source_id,),
            ).fetchone()
            if row is None or not _stored_source_matches(row, fingerprint):
                return False
            if int(row[7]) != fingerprint.frame_count or str(row[8]) != "ready":
                return False
            if not self._content_matches_after_timestamp_change(row, fingerprint):
                return False
            if int(row[5]) != fingerprint.mtime_ns:
                connection.execute(
                    """
                    UPDATE sources
                    SET mtime_ns = ?, updated_at_utc = ?
                    WHERE source_id = ?
                    """,
                    (fingerprint.mtime_ns, _utc_now(), fingerprint.source_id),
                )
                connection.commit()
            return True

    def rebuild_session(
        self,
        project: CrtProject,
        session: SessionRecord,
        *,
        session_path: str | Path | None = None,
        progress: Callable[[int, int], None] | None = None,
        cancel_event: Event | None = None,
        batch_size: int = 1_000,
    ) -> SessionSearchFingerprint:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        path = (
            Path(session_path).resolve()
            if session_path is not None
            else project.absolute_path(session.relative_path)
        )
        fingerprint = self.fingerprint(project, session, path)
        reader = SessionPagedReader(path)
        if reader.frame_count != fingerprint.frame_count:
            fingerprint = SessionSearchFingerprint(
                source_id=fingerprint.source_id,
                session_id=fingerprint.session_id,
                relative_path=fingerprint.relative_path,
                sha256=fingerprint.sha256,
                file_size=fingerprint.file_size,
                mtime_ns=fingerprint.mtime_ns,
                frame_count=reader.frame_count,
            )

        start_row = self._begin_or_resume(fingerprint)
        total = fingerprint.frame_count
        if progress is not None:
            progress(start_row, total)

        batch: list[tuple[object, ...]] = []
        indexed = start_row
        try:
            for source_row, frame in enumerate(
                reader.iter_frames(start=start_row),
                start=start_row,
            ):
                if cancel_event is not None and cancel_event.is_set():
                    self._set_source_status(
                        fingerprint.source_id,
                        "pending",
                        indexed_rows=indexed,
                    )
                    return fingerprint
                batch.append(_document_row(fingerprint.source_id, source_row, frame))
                if len(batch) >= batch_size:
                    self._append_batch(fingerprint.source_id, batch, source_row + 1)
                    indexed = source_row + 1
                    batch.clear()
                    if progress is not None:
                        progress(indexed, total)

            if batch:
                self._append_batch(fingerprint.source_id, batch, total)
                indexed = total
            self._set_source_status(
                fingerprint.source_id,
                "ready",
                indexed_rows=total,
                error="",
            )
            if progress is not None:
                progress(total, total)
            return fingerprint
        except Exception as exc:
            self._set_source_status(
                fingerprint.source_id,
                "failed",
                indexed_rows=indexed,
                error=str(exc),
            )
            raise

    def source(self, source_id: str) -> "SqliteSessionQuerySource":
        return SqliteSessionQuerySource(self.path, source_id)

    def remove_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sources WHERE session_id = ?", (session_id,))
            connection.commit()

    def _begin_or_resume(self, fingerprint: SessionSearchFingerprint) -> int:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT session_id, relative_path, schema_version, sha256,
                       file_size, mtime_ns, frame_count, indexed_rows
                FROM sources WHERE source_id = ?
                """,
                (fingerprint.source_id,),
            ).fetchone()
            resume = 0
            if row is not None:
                same = _stored_source_matches(row, fingerprint)
                if same:
                    same = self._content_matches_after_timestamp_change(row, fingerprint)
                if same:
                    resume = max(0, min(int(row[7]), fingerprint.frame_count))
                    count = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM documents WHERE source_id = ?",
                            (fingerprint.source_id,),
                        ).fetchone()[0]
                    )
                    if count != resume:
                        resume = 0
                if not same or resume == 0:
                    connection.execute(
                        "DELETE FROM documents WHERE source_id = ?",
                        (fingerprint.source_id,),
                    )
            connection.execute(
                """
                INSERT INTO sources(
                    source_id, session_id, relative_path, source_kind,
                    schema_version, sha256, file_size, mtime_ns, frame_count,
                    indexed_rows, status, error, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'building', '', ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    relative_path = excluded.relative_path,
                    source_kind = excluded.source_kind,
                    schema_version = excluded.schema_version,
                    sha256 = excluded.sha256,
                    file_size = excluded.file_size,
                    mtime_ns = excluded.mtime_ns,
                    frame_count = excluded.frame_count,
                    indexed_rows = excluded.indexed_rows,
                    status = 'building',
                    error = '',
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    fingerprint.source_id,
                    fingerprint.session_id,
                    fingerprint.relative_path,
                    SEARCH_SOURCE_KIND,
                    fingerprint.schema_version,
                    fingerprint.sha256,
                    fingerprint.file_size,
                    fingerprint.mtime_ns,
                    fingerprint.frame_count,
                    resume,
                    _utc_now(),
                ),
            )
            connection.commit()
        return resume

    def _content_matches_after_timestamp_change(
        self,
        row: tuple[object, ...],
        fingerprint: SessionSearchFingerprint,
    ) -> bool:
        if int(row[5]) == fingerprint.mtime_ns:
            return True
        expected_sha = str(row[3] or "")
        if not expected_sha or expected_sha != fingerprint.sha256:
            return False
        source_path = (self.project_root / fingerprint.relative_path).resolve()
        try:
            source_path.relative_to(self.project_root)
        except ValueError:
            return False
        return source_path.is_file() and _sha256(source_path) == expected_sha

    def _append_batch(
        self,
        source_id: str,
        rows: list[tuple[object, ...]],
        indexed_rows: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                """
                INSERT OR REPLACE INTO documents(
                    source_id, record_id, source_row, sequence, timestamp_ns,
                    arbitration_id, timestamp_text, timestamp_norm,
                    sequence_text, sequence_norm, can_id_text, can_id_norm,
                    type_text, type_norm, dlc_text, dlc_norm, data_text,
                    data_norm, channel_text, channel_norm, flags_text, flags_norm
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                rows,
            )
            connection.execute(
                """
                UPDATE sources
                SET indexed_rows = ?, updated_at_utc = ?
                WHERE source_id = ?
                """,
                (indexed_rows, _utc_now(), source_id),
            )
            connection.commit()

    def _set_source_status(
        self,
        source_id: str,
        status: str,
        *,
        indexed_rows: int,
        error: str = "",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sources
                SET status = ?, indexed_rows = ?, error = ?, updated_at_utc = ?
                WHERE source_id = ?
                """,
                (status, indexed_rows, error, _utc_now(), source_id),
            )
            connection.commit()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS sources(
                    source_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL UNIQUE,
                    relative_path TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    sha256 TEXT NOT NULL DEFAULT '',
                    file_size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    frame_count INTEGER NOT NULL,
                    indexed_rows INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents(
                    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
                    record_id TEXT NOT NULL,
                    source_row INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    timestamp_ns INTEGER NOT NULL,
                    arbitration_id INTEGER NOT NULL,
                    timestamp_text TEXT NOT NULL,
                    timestamp_norm TEXT NOT NULL,
                    sequence_text TEXT NOT NULL,
                    sequence_norm TEXT NOT NULL,
                    can_id_text TEXT NOT NULL,
                    can_id_norm TEXT NOT NULL,
                    type_text TEXT NOT NULL,
                    type_norm TEXT NOT NULL,
                    dlc_text TEXT NOT NULL,
                    dlc_norm TEXT NOT NULL,
                    data_text TEXT NOT NULL,
                    data_norm TEXT NOT NULL,
                    channel_text TEXT NOT NULL,
                    channel_norm TEXT NOT NULL,
                    flags_text TEXT NOT NULL,
                    flags_norm TEXT NOT NULL,
                    PRIMARY KEY(source_id, record_id),
                    UNIQUE(source_id, source_row)
                );

                CREATE INDEX IF NOT EXISTS idx_search_documents_source_row
                    ON documents(source_id, source_row);
                CREATE INDEX IF NOT EXISTS idx_search_documents_can_id
                    ON documents(source_id, arbitration_id);
                CREATE INDEX IF NOT EXISTS idx_search_documents_sequence
                    ON documents(source_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_search_documents_timestamp
                    ON documents(source_id, timestamp_ns);
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection


class SqliteSessionQuerySource:
    """Query source that keeps persistent documents in SQLite instead of RAM."""

    headers = list(SEARCH_HEADERS)

    def __init__(self, database_path: str | Path, source_id: str) -> None:
        self.database_path = Path(database_path)
        self.source_id = source_id

    def snapshot(self) -> "SqliteSessionQuerySource":
        return self

    def __len__(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT indexed_rows FROM sources WHERE source_id = ? AND status = 'ready'",
                (self.source_id,),
            ).fetchone()
        return 0 if row is None else int(row[0])

    def __iter__(self) -> Iterator[SearchDocument]:
        query = self._select_sql()
        with self._connect() as connection:
            cursor = connection.execute(query, (self.source_id,))
            for row in cursor:
                yield _search_document_from_row(row)

    def execute_search(
        self,
        search_engine: SearchEngine,
        query: SearchQuery | CompiledSearchQuery,
        *,
        preview_limit: int,
        result_limit: int | None,
        should_cancel: Callable[[], bool] | None,
    ) -> tuple[tuple[SearchHit, ...], int]:
        compiled = query if isinstance(query, CompiledSearchQuery) else search_engine.compile(query)
        where_sql, parameters = _candidate_where(compiled)
        sql = self._select_sql(where_sql)
        hits: list[SearchHit] = []
        scanned = 0
        with self._connect() as connection:
            cursor = connection.execute(sql, (self.source_id, *parameters))
            for row in cursor:
                if should_cancel is not None and scanned % 256 == 0 and should_cancel():
                    return (), scanned
                document = _search_document_from_row(row)
                scanned += 1
                matched, matched_fields, matched_terms, fields = compiled.match_document(document)
                if not matched:
                    continue
                hits.append(
                    SearchHit(
                        row=document.row,
                        preview=" | ".join(value for _, value in fields)[:preview_limit],
                        matched_fields=matched_fields,
                        matched_terms=matched_terms,
                    )
                )
                if result_limit is not None and len(hits) >= result_limit:
                    break
        return tuple(hits), scanned

    def _select_sql(self, extra_where: str = "") -> str:
        columns = ", ".join(_RAW_SELECT_COLUMNS)
        suffix = f" AND ({extra_where})" if extra_where else ""
        return (
            f"SELECT source_row, {columns} FROM documents "
            f"WHERE source_id = ?{suffix} ORDER BY source_row"
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection


class FailedQuerySource:
    """Worker-safe source used to surface a persistent-index build failure."""

    def __init__(self, error: str) -> None:
        self.error = error

    def snapshot(self) -> "FailedQuerySource":
        return self

    def execute_search(self, *_args, **_kwargs):
        raise RuntimeError(self.error)


def _stored_source_matches(
    row: tuple[object, ...],
    fingerprint: SessionSearchFingerprint,
) -> bool:
    return (
        str(row[0]) == fingerprint.session_id
        and str(row[1]) == fingerprint.relative_path
        and int(row[2]) == fingerprint.schema_version
        and str(row[3] or "") == fingerprint.sha256
        and int(row[4]) == fingerprint.file_size
        and int(row[6]) == fingerprint.frame_count
    )


def _candidate_where(compiled: CompiledSearchQuery) -> tuple[str, tuple[str, ...]]:
    query = compiled.query
    if query.case_sensitive or query.mode in (SearchMode.REGEX, SearchMode.WILDCARD):
        return "", ()

    selected = tuple(query.fields) if query.fields else SEARCH_HEADERS
    columns = [
        _FIELD_COLUMNS[name][1]
        for name in selected
        if name in _FIELD_COLUMNS
    ]
    if not columns:
        return "0", ()

    term_clauses: list[str] = []
    parameters: list[str] = []
    for term in compiled.terms:
        alternatives = tuple(getattr(term, "_alternatives", (term.text.casefold(),)))
        alternative_clauses: list[str] = []
        for alternative in alternatives:
            field_clauses: list[str] = []
            for column in columns:
                if query.mode == SearchMode.EXACT:
                    field_clauses.append(f"{column} = ?")
                    parameters.append(alternative)
                elif query.mode == SearchMode.PREFIX:
                    field_clauses.append(f"instr({column}, ?) = 1")
                    parameters.append(alternative)
                elif query.mode == SearchMode.SUFFIX:
                    field_clauses.append(f"substr({column}, -length(?)) = ?")
                    parameters.extend((alternative, alternative))
                else:
                    field_clauses.append(f"instr({column}, ?) > 0")
                    parameters.append(alternative)
            alternative_clauses.append("(" + " OR ".join(field_clauses) + ")")
        term_clauses.append("(" + " OR ".join(alternative_clauses) + ")")

    joiner = " AND " if compiled.logic == SearchLogic.ALL else " OR "
    return joiner.join(term_clauses), tuple(parameters)


def _search_document_from_row(row: tuple[object, ...]) -> SearchDocument:
    return SearchDocument(
        row=int(row[0]),
        fields={
            header: str(value or "")
            for header, value in zip(SEARCH_HEADERS, row[1:], strict=True)
        },
    )


def _document_row(source_id: str, source_row: int, frame) -> tuple[object, ...]:
    timestamp_text = f"{frame.timestamp_ns / 1_000_000:.3f}"
    sequence_text = str(frame.sequence)
    width = 8 if frame.is_extended_id else 3
    can_id_text = f"0x{frame.arbitration_id:0{width}X}"
    type_text = "EXT" if frame.is_extended_id else "STD"
    dlc_text = str(frame.dlc)
    data_text = frame.data_hex
    channel_text = str(frame.channel)
    flags: list[str] = []
    if frame.is_remote_frame:
        flags.append("RTR")
    if frame.is_error_frame:
        flags.append("ERR")
    if frame.source_flags:
        flags.append(f"0x{frame.source_flags:X}")
    flags_text = ", ".join(flags)
    return (
        source_id,
        str(frame.sequence),
        int(source_row),
        int(frame.sequence),
        int(frame.timestamp_ns),
        int(frame.arbitration_id),
        timestamp_text,
        timestamp_text.casefold(),
        sequence_text,
        sequence_text.casefold(),
        can_id_text,
        can_id_text.casefold(),
        type_text,
        type_text.casefold(),
        dlc_text,
        dlc_text.casefold(),
        data_text,
        data_text.casefold(),
        channel_text,
        channel_text.casefold(),
        flags_text,
        flags_text.casefold(),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
