from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .project import CrtProject, SessionRecord
from .session_stream import read_session_header


@dataclass(frozen=True, slots=True)
class SessionRemovalResult:
    session: SessionRecord
    removed_files: tuple[Path, ...]
    missing_files: tuple[Path, ...]


def session_artifact_paths(project: CrtProject, session: SessionRecord) -> tuple[Path, ...]:
    """Return every project-owned file associated with one CAN session.

    Both Live and imported sessions own a primary ``*.crt.jsonl`` stream plus
    optional raw-frame, logical-message, marker and sparse-index sidecars. CSV
    imports additionally own the copy placed in ``sessions/imported/source``;
    its project-relative path is stored in the CRT session header.

    Every returned path is constrained to the project root. An external source
    path can therefore never be deleted, even if a malformed or future session
    header happens to contain one.
    """

    primary = project.absolute_path(session.relative_path)
    name = primary.name
    if name.lower().endswith(".crt.jsonl"):
        base = name[: -len(".crt.jsonl")]
    else:
        base = primary.stem

    candidates: list[Path] = [
        primary,
        primary.with_name(f"{base}.frames.csv"),
        primary.with_name(f"{base}.messages.csv"),
        primary.with_name(f"{base}.markers.jsonl"),
        primary.with_suffix(primary.suffix + ".idx.json"),
    ]

    if session.source.startswith("imported") and primary.is_file():
        try:
            header = read_session_header(primary)
            original_file = header.metadata.get("original_file")
            if isinstance(original_file, str) and original_file.strip():
                candidates.append(project.absolute_path(original_file))
        except (OSError, ValueError, KeyError, TypeError):
            # The indexed session and its standard sidecars can still be removed
            # even when an old or damaged header cannot expose the imported copy.
            pass

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
    """Remove a session from the project index and optionally its project files.

    ``delete_files`` affects only paths owned by the CRT project. The original
    file selected by the user during import lives outside the project and is not
    part of ``session_artifact_paths``.
    """

    session = _session_by_id(project, session_id)
    if session is None:
        raise KeyError(f"nie znaleziono sesji: {session_id}")

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
