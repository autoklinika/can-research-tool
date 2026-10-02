from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .project import CrtProject, SessionRecord
from .project_search_index import ProjectSearchIndex
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
    """Remove a session, its project files and its rebuildable search records."""

    session = _session_by_id(project, session_id)
    if session is None:
        raise KeyError(f"nie znaleziono sesji: {session_id}")

    artifacts = session_artifact_paths(project, session) if delete_files else ()
    for path in artifacts:
        if path.exists() and not (path.is_file() or path.is_symlink()):
            raise IsADirectoryError(path)

    removed: list[Path] = []
    missing: list[Path] = []
    # Files are first *moved* into a per-removal staging folder. A rename is
    # reversible, so a failure on any artifact (for example a file locked by
    # another program on Windows) restores the already-moved files and rolls
    # the database back. Only after the commit are staged files deleted.
    staged: list[tuple[Path, Path]] = []
    staging_dir = project.root / ".crt" / "trash" / f"{session.id}-{uuid4().hex}"
    connection = sqlite3.connect(project.database_path, timeout=30.0)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (session.id,))
        if cursor.rowcount != 1:
            raise KeyError(f"nie znaleziono sesji: {session.id}")

        for index, path in enumerate(artifacts):
            if path.exists() or path.is_symlink():
                staging_dir.mkdir(parents=True, exist_ok=True)
                target = staging_dir / f"{index:02d}-{path.name}"
                path.rename(target)
                staged.append((path, target))
                removed.append(path)
            else:
                missing.append(path)
        connection.commit()
    except Exception:
        connection.rollback()
        _restore_staged(staged)
        _remove_empty_dir(staging_dir)
        raise
    finally:
        connection.close()

    for _original, target in staged:
        try:
            target.unlink()
        except OSError:
            # The session is already gone from the project; a leftover file in
            # .crt/trash is harmless and can be removed manually.
            pass
    _remove_empty_dir(staging_dir)

    try:
        ProjectSearchIndex(project).remove_session(session.id)
    except (OSError, sqlite3.Error):
        # Search data is a disposable cache. Failure to clean it must not turn a
        # successful source-session deletion into a user-visible failure.
        pass

    return SessionRemovalResult(
        session=session,
        removed_files=tuple(removed),
        missing_files=tuple(missing),
    )


def _restore_staged(staged: list[tuple[Path, Path]]) -> None:
    for original, target in reversed(staged):
        try:
            target.rename(original)
        except OSError:
            pass


def _remove_empty_dir(path: Path) -> None:
    try:
        path.rmdir()
        path.parent.rmdir()
    except OSError:
        pass


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
