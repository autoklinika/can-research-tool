from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


class ClosingSqliteConnection(sqlite3.Connection):
    """SQLite connection whose context manager also releases the file handle.

    ``sqlite3.Connection.__exit__`` commits or rolls back a transaction but does
    not close the connection. That distinction is mostly invisible on POSIX,
    where an open database file can still be unlinked, but it leaves CRT SQLite
    files locked on Windows until garbage collection eventually runs.
    """

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()


class ClosingSqliteModule:
    """Module proxy applying ``ClosingSqliteConnection`` to one consumer."""

    def __init__(self, module: ModuleType = sqlite3) -> None:
        self._module = module

    def connect(self, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        kwargs.setdefault("factory", ClosingSqliteConnection)
        return self._module.connect(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._module, name)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stored_source_matches(self, row: tuple[object, ...], fingerprint) -> bool:
    """Return whether source identity and immutable content metadata match.

    A file timestamp is deliberately not part of this first comparison. Windows
    utilities, antivirus software and synchronisation tools may touch metadata
    without changing the project-owned session content.
    """

    return (
        str(row[0]) == fingerprint.session_id
        and str(row[1]) == fingerprint.relative_path
        and int(row[2]) == fingerprint.schema_version
        and str(row[3] or "") == fingerprint.sha256
        and int(row[4]) == fingerprint.file_size
        and int(row[6]) == fingerprint.frame_count
    )


def _content_matches_after_timestamp_change(self, row, fingerprint) -> bool:
    stored_mtime = int(row[5])
    if stored_mtime == fingerprint.mtime_ns:
        return True

    expected_sha = str(row[3] or "")
    if not expected_sha or expected_sha != fingerprint.sha256:
        return False

    source_path = (Path(self.project_root) / fingerprint.relative_path).resolve()
    try:
        source_path.relative_to(Path(self.project_root).resolve())
    except ValueError:
        return False
    if not source_path.is_file():
        return False
    return _sha256(source_path) == expected_sha


def _stable_is_current(self, fingerprint) -> bool:
    with self._connect() as connection:
        row = connection.execute(
            """
            SELECT session_id, relative_path, schema_version, sha256,
                   file_size, mtime_ns, frame_count, indexed_rows, status
            FROM sources WHERE source_id = ?
            """,
            (fingerprint.source_id,),
        ).fetchone()
        if row is None or not _stored_source_matches(self, row, fingerprint):
            return False
        if int(row[7]) != fingerprint.frame_count or str(row[8]) != "ready":
            return False
        if not _content_matches_after_timestamp_change(self, row, fingerprint):
            return False
        if int(row[5]) != fingerprint.mtime_ns:
            connection.execute(
                """
                UPDATE sources
                SET mtime_ns = ?, updated_at_utc = ?
                WHERE source_id = ?
                """,
                (
                    fingerprint.mtime_ns,
                    datetime.now(timezone.utc).isoformat(),
                    fingerprint.source_id,
                ),
            )
            connection.commit()
        return True


def _stable_begin_or_resume(self, fingerprint) -> int:
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
            same = _stored_source_matches(self, row, fingerprint)
            if same:
                same = _content_matches_after_timestamp_change(self, row, fingerprint)
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
                "raw-can-frames",
                fingerprint.schema_version,
                fingerprint.sha256,
                fingerprint.file_size,
                fingerprint.mtime_ns,
                fingerprint.frame_count,
                resume,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
    return resume


def install_project_search_index_sqlite_lifecycle() -> None:
    """Install deterministic SQLite lifecycle and stable index validation.

    Context-managed connections are closed explicitly on Windows. Persistent
    search indexes also survive metadata-only timestamp changes: when ``mtime``
    differs, CRT verifies the project session SHA-256 before deciding whether a
    rebuild is necessary.

    The historical function name is retained to avoid changing package startup
    imports.
    """

    from . import project, project_search_index

    for consumer in (project, project_search_index):
        if not isinstance(consumer.sqlite3, ClosingSqliteModule):
            consumer.sqlite3 = ClosingSqliteModule(consumer.sqlite3)

    index_class = project_search_index.ProjectSearchIndex
    if not bool(getattr(index_class, "_stable_fingerprint_policy_installed", False)):
        index_class.is_current = _stable_is_current
        index_class._begin_or_resume = _stable_begin_or_resume
        index_class._stable_fingerprint_policy_installed = True
