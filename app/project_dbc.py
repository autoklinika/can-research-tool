from __future__ import annotations

import hashlib
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .dbc import DbcFileRecord, inspect_dbc


def list_project_dbc(project) -> list[DbcFileRecord]:
    _ensure_schema(project)
    with _connect(project) as connection:
        rows = connection.execute(
            """
            SELECT id, name, relative_path, enabled, message_count, sha256, added_at_utc
            FROM dbc_files
            ORDER BY added_at_utc, name COLLATE NOCASE
            """
        ).fetchall()
    return [
        DbcFileRecord(
            id=str(row[0]),
            name=str(row[1]),
            relative_path=str(row[2]),
            enabled=bool(row[3]),
            message_count=int(row[4]),
            sha256=str(row[5]),
            added_at_utc=str(row[6]),
        )
        for row in rows
    ]


def import_project_dbc(project, source_path: str | Path) -> DbcFileRecord:
    source = Path(source_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() != ".dbc":
        raise ValueError("wybierz plik z rozszerzeniem .dbc")

    inspection = inspect_dbc(source)
    digest = _sha256(source)
    existing = next((item for item in list_project_dbc(project) if item.sha256 == digest), None)
    if existing is not None:
        return existing

    target_directory = Path(project.root) / "decoders" / "dbc"
    target_directory.mkdir(parents=True, exist_ok=True)
    target = _unique_path(target_directory / source.name)
    shutil.copy2(source, target)
    relative = project.relative_path(target)
    record = DbcFileRecord(
        id=str(uuid4()),
        name=source.stem,
        relative_path=relative,
        enabled=True,
        message_count=inspection.message_count,
        sha256=digest,
        added_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    _ensure_schema(project)
    with _connect(project) as connection:
        connection.execute(
            """
            INSERT INTO dbc_files(
                id, name, relative_path, enabled, message_count, sha256, added_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.name,
                record.relative_path,
                int(record.enabled),
                record.message_count,
                record.sha256,
                record.added_at_utc,
            ),
        )
        connection.commit()
    return record


def set_project_dbc_enabled(project, dbc_id: str, enabled: bool) -> None:
    _ensure_schema(project)
    with _connect(project) as connection:
        cursor = connection.execute(
            "UPDATE dbc_files SET enabled = ? WHERE id = ?",
            (int(enabled), dbc_id),
        )
        connection.commit()
    if cursor.rowcount != 1:
        raise KeyError(f"nie znaleziono pliku DBC: {dbc_id}")


def remove_project_dbc(project, dbc_id: str) -> None:
    _ensure_schema(project)
    with _connect(project) as connection:
        row = connection.execute(
            "SELECT relative_path FROM dbc_files WHERE id = ?",
            (dbc_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"nie znaleziono pliku DBC: {dbc_id}")
        connection.execute("DELETE FROM dbc_files WHERE id = ?", (dbc_id,))
        connection.commit()
    path = project.absolute_path(str(row[0]))
    if path.is_file():
        path.unlink()


def active_project_dbc_paths(project) -> tuple[Path, ...]:
    return tuple(
        project.absolute_path(record.relative_path)
        for record in list_project_dbc(project)
        if record.enabled
    )


def _ensure_schema(project) -> None:
    Path(project.root, "decoders", "dbc").mkdir(parents=True, exist_ok=True)
    with _connect(project) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dbc_files(
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                relative_path TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                message_count INTEGER NOT NULL DEFAULT 0,
                sha256 TEXT NOT NULL UNIQUE,
                added_at_utc TEXT NOT NULL
            )
            """
        )
        connection.commit()


def _connect(project) -> sqlite3.Connection:
    connection = sqlite3.connect(project.database_path, timeout=30.0)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1
