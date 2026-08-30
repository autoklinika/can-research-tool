from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import sqlite_connection as sqlite3
from .project import CrtProject, SessionRecord
from .project_search_index import ProjectSearchIndex
from .session_stream import SessionPagedReader


class ComparisonEvidenceCancelled(RuntimeError):
    """Raised when locating comparison evidence is cancelled."""


@dataclass(frozen=True, slots=True)
class ParsedMessageKey:
    channel: int
    arbitration_id: int
    is_extended_id: bool
    is_remote_frame: bool
    is_error_frame: bool


@dataclass(frozen=True, slots=True)
class ComparisonEvidenceLocation:
    session_id: str
    session_path: Path
    source_row: int
    message_key: str


def parse_message_key(value: str) -> ParsedMessageKey:
    parts = str(value).strip().split(":")
    if len(parts) != 4:
        raise ValueError(f"Niepoprawny klucz wiadomości porównania: {value!r}")
    channel_text, format_text, arbitration_text, kind_text = parts
    try:
        channel = int(channel_text, 10)
        arbitration_id = int(arbitration_text, 16)
    except ValueError as exc:
        raise ValueError(
            f"Niepoprawny klucz wiadomości porównania: {value!r}"
        ) from exc

    normalized_format = format_text.upper()
    if normalized_format not in {"STD", "EXT"}:
        raise ValueError(
            f"Niepoprawny format klucza wiadomości: {format_text!r}"
        )
    maximum_arbitration_id = (
        0x1FFFFFFF if normalized_format == "EXT" else 0x7FF
    )
    if channel < 0 or not 0 <= arbitration_id <= maximum_arbitration_id:
        raise ValueError(f"Niepoprawny klucz wiadomości porównania: {value!r}")

    normalized_kind = kind_text.casefold()
    if normalized_kind not in {"data", "remote", "error"}:
        raise ValueError(f"Niepoprawny typ ramki w kluczu: {kind_text!r}")
    return ParsedMessageKey(
        channel=channel,
        arbitration_id=arbitration_id,
        is_extended_id=normalized_format == "EXT",
        is_remote_frame=normalized_kind == "remote",
        is_error_frame=normalized_kind == "error",
    )


def locate_comparison_evidence(
    project: CrtProject,
    session_id: str,
    message_key: str,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> ComparisonEvidenceLocation:
    session = _session(project, session_id)
    session_path = project.absolute_path(session.relative_path)
    parsed = parse_message_key(message_key)
    _raise_if_cancelled(should_cancel)

    source_row = _locate_in_search_index(
        project,
        session,
        session_path,
        parsed,
        should_cancel=should_cancel,
    )
    if source_row is None:
        source_row = _locate_in_session(
            session_path,
            parsed,
            should_cancel=should_cancel,
        )
    if source_row is None:
        raise LookupError(
            f"Nie znaleziono klucza wiadomości {message_key!r} "
            f"w sesji {session.name!r}."
        )
    return ComparisonEvidenceLocation(
        session_id=session.id,
        session_path=session_path,
        source_row=source_row,
        message_key=message_key,
    )


def _session(project: CrtProject, session_id: str) -> SessionRecord:
    record = next(
        (item for item in project.list_sessions() if item.id == session_id),
        None,
    )
    if record is None:
        raise LookupError(f"Nie znaleziono sesji porównawczej: {session_id!r}.")
    return record


def _locate_in_search_index(
    project: CrtProject,
    session: SessionRecord,
    session_path: Path,
    key: ParsedMessageKey,
    *,
    should_cancel: Callable[[], bool] | None,
) -> int | None:
    index = ProjectSearchIndex(project)
    fingerprint = index.fingerprint(project, session, session_path)
    if not index.is_current(fingerprint):
        return None
    _raise_if_cancelled(should_cancel)

    if key.is_error_frame:
        kind_clause = "instr(lower(flags_text), 'err') > 0"
    elif key.is_remote_frame:
        kind_clause = (
            "instr(lower(flags_text), 'rtr') > 0 "
            "AND instr(lower(flags_text), 'err') = 0"
        )
    else:
        kind_clause = (
            "instr(lower(flags_text), 'rtr') = 0 "
            "AND instr(lower(flags_text), 'err') = 0"
        )
    sql = f"""
        SELECT source_row
        FROM documents
        WHERE source_id = ?
          AND arbitration_id = ?
          AND channel_text = ?
          AND type_text = ?
          AND {kind_clause}
        ORDER BY source_row
        LIMIT 1
    """
    with sqlite3.connect(index.path, timeout=30.0) as connection:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        row = connection.execute(
            sql,
            (
                fingerprint.source_id,
                key.arbitration_id,
                str(key.channel),
                "EXT" if key.is_extended_id else "STD",
            ),
        ).fetchone()
    _raise_if_cancelled(should_cancel)
    return None if row is None else int(row[0])


def _locate_in_session(
    session_path: Path,
    key: ParsedMessageKey,
    *,
    should_cancel: Callable[[], bool] | None,
) -> int | None:
    reader = SessionPagedReader(session_path)
    for source_row, frame in enumerate(reader.iter_frames()):
        if source_row % 1024 == 0:
            _raise_if_cancelled(should_cancel)
        if (
            frame.channel == key.channel
            and frame.arbitration_id == key.arbitration_id
            and frame.is_extended_id == key.is_extended_id
            and _frame_kind_matches(frame, key)
        ):
            return source_row
    _raise_if_cancelled(should_cancel)
    return None


def _frame_kind_matches(frame, key: ParsedMessageKey) -> bool:
    if key.is_error_frame:
        return bool(frame.is_error_frame)
    if key.is_remote_frame:
        return bool(frame.is_remote_frame) and not frame.is_error_frame
    return not frame.is_remote_frame and not frame.is_error_frame


def _raise_if_cancelled(
    should_cancel: Callable[[], bool] | None,
) -> None:
    if should_cancel is not None and should_cancel():
        raise ComparisonEvidenceCancelled
