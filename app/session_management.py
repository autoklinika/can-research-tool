from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .project import CrtProject, SessionRecord


@dataclass(frozen=True, slots=True)
class SessionRemovalResult:
    session: SessionRecord
    removed_files: tuple[Path, ...]
    missing_files: tuple[Path, ...]


def session_artifact_paths(project: CrtProject, session: SessionRecord) -> tuple[Path, ...]:
    """Return the files owned by one Live Capture session.

    A live session is stored as a primary ``*.crt.jsonl`` stream plus optional
    raw-frame, logical-message and marker sidecars. The paths are derived from
    the indexed primary path and are always constrained to the project root.
    """

    primary = project.absolute_path(session.relative_path)
    name = primary.name
    if name.lower().endswith(".crt.jsonl"):
        base = name[: -len(".crt.jsonl")]
    else:
        base = primary.stem

    candidates = (
        primary,
        primary.with_name(f"{base}.frames.csv"),
        primary.with_name(f"{base}.messages.csv"),
        primary.with_name(f"{base}.markers.jsonl"),
    )
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        project.relative_path(resolved)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return tuple(unique)


def remove_session(
    project: CrtProject,
    session_id: str,
    *,
    delete_files: bool,
) -> SessionRemovalResult:
    """Remove a session from the project index and optionally delete its files.

    Imported sessions intentionally support index-only removal. Deleting files
    for an imported record is rejected so a GUI regression cannot destroy the
    preserved imported source or the project's imported copy.
    """

    session = _session_by_id(project, session_id)
    if session is None:
        raise KeyError(f"nie znaleziono sesji: {session_id}")
    if delete_files and session.source.startswith("imported"):
        raise ValueError("importowaną sesję można usunąć wyłącznie z listy")

    artifacts = session_artifact_paths(project, session) if delete_files else ()
    for path in artifacts:
        if path.exists() and not (path.is_file() or path.is_symlink()):
            raise IsADirectoryError(path)

    removed: list[Path] = []
    missing: list[Path] = []
    connection = sqlite3.connect(project.database_path, timeout=30.0)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (session.id,))
        if cursor.rowcount != 1:
            raise KeyError(f"nie znaleziono sesji: {session.id}")

        for path in artifacts:
            if path.exists() or path.is_symlink():
                path.unlink()
                removed.append(path)
            else:
                missing.append(path)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return SessionRemovalResult(
        session=session,
        removed_files=tuple(removed),
        missing_files=tuple(missing),
    )


def _session_by_id(project: CrtProject, session_id: str) -> SessionRecord | None:
    connection = sqlite3.connect(project.database_path, timeout=30.0)
    try:
        row = connection.execute(
            """
            SELECT id, name, relative_path, source, status, created_at_utc,
                   frame_count, marker_count, duration_s, sha256
            FROM sessions WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else SessionRecord(*row)
