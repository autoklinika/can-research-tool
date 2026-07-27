from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from .domain import ComparisonSet
from .project import CrtProject, SessionRecord
from .session_stream import SessionPagedReader

SYNC_SESSION_START = "session_start"
SYNC_MESSAGE_KEY = "message_key"
DEFAULT_MAX_EVENTS_PER_SESSION = 2_000
_CANCEL_CHECK_INTERVAL = 1_024


class ComparisonTimelineCancelled(RuntimeError):
    """Raised when timeline construction is cancelled."""


@dataclass(frozen=True, slots=True)
class TimelineMessageKey:
    channel: int
    arbitration_id: int
    is_extended_id: bool
    frame_kind: str


@dataclass(frozen=True, slots=True)
class ComparisonTimelineEvent:
    session_id: str
    session_name: str
    source_row: int
    sequence: int
    timestamp_ns: int
    relative_time_ns: int | None
    message_key: str
    data_hex: str
    dlc: int


@dataclass(frozen=True, slots=True)
class ComparisonTimelineLane:
    session_id: str
    session_name: str
    total_frame_count: int
    sampled_frame_count: int
    sample_stride: int
    anchor_source_row: int | None
    anchor_timestamp_ns: int | None
    first_timestamp_ns: int | None
    last_timestamp_ns: int | None
    synchronized: bool
    warning: str
    events: tuple[ComparisonTimelineEvent, ...]


@dataclass(frozen=True, slots=True)
class ComparisonTimelineResult:
    synchronization_mode: str
    anchor_message_key: str
    lanes: tuple[ComparisonTimelineLane, ...]
    warnings: tuple[str, ...]
    minimum_relative_time_ns: int
    maximum_relative_time_ns: int


@dataclass(frozen=True, slots=True)
class _PendingEvent:
    source_row: int
    sequence: int
    timestamp_ns: int
    message_key: str
    data_hex: str
    dlc: int


def build_comparison_timeline(
    project: CrtProject,
    comparison_set: ComparisonSet,
    *,
    synchronization_mode: str = SYNC_SESSION_START,
    anchor_message_key: str = "",
    max_events_per_session: int = DEFAULT_MAX_EVENTS_PER_SESSION,
    should_cancel: Callable[[], bool] | None = None,
) -> ComparisonTimelineResult:
    """Build a bounded, passive timeline without modifying source sessions."""

    if synchronization_mode not in {SYNC_SESSION_START, SYNC_MESSAGE_KEY}:
        raise ValueError(f"Nieobsługiwany tryb synchronizacji: {synchronization_mode!r}")
    if max_events_per_session <= 0:
        raise ValueError("max_events_per_session must be greater than zero")

    normalized_anchor = anchor_message_key.strip()
    parsed_anchor = None
    if synchronization_mode == SYNC_MESSAGE_KEY:
        if not normalized_anchor:
            raise ValueError("Podaj klucz wiadomości używany jako kotwica synchronizacji.")
        parsed_anchor = parse_timeline_message_key(normalized_anchor)
        normalized_anchor = format_timeline_message_key(parsed_anchor)

    records = {record.id: record for record in project.list_sessions()}
    lanes: list[ComparisonTimelineLane] = []
    warnings: list[str] = []
    relative_values: list[int] = []

    for session_id in comparison_set.session_ids:
        _raise_if_cancelled(should_cancel)
        record = records.get(session_id)
        if record is None:
            warning = f"Nie znaleziono sesji należącej do zestawu: {session_id}."
            warnings.append(warning)
            lanes.append(_missing_lane(session_id, warning))
            continue

        lane = _build_lane(
            project,
            record,
            synchronization_mode=synchronization_mode,
            anchor=parsed_anchor,
            max_events=max_events_per_session,
            should_cancel=should_cancel,
        )
        lanes.append(lane)
        if lane.warning:
            warnings.append(lane.warning)
        relative_values.extend(
            event.relative_time_ns
            for event in lane.events
            if event.relative_time_ns is not None
        )

    _raise_if_cancelled(should_cancel)
    minimum = min(relative_values, default=0)
    maximum = max(relative_values, default=0)
    if minimum == maximum:
        maximum = minimum + 1

    return ComparisonTimelineResult(
        synchronization_mode=synchronization_mode,
        anchor_message_key=normalized_anchor,
        lanes=tuple(lanes),
        warnings=tuple(warnings),
        minimum_relative_time_ns=minimum,
        maximum_relative_time_ns=maximum,
    )


def parse_timeline_message_key(value: str) -> TimelineMessageKey:
    parts = str(value).strip().split(":")
    if len(parts) != 4:
        raise ValueError(f"Niepoprawny klucz wiadomości: {value!r}")
    channel_text, format_text, arbitration_text, kind_text = parts
    try:
        channel = int(channel_text, 10)
        arbitration_id = int(arbitration_text, 16)
    except ValueError as exc:
        raise ValueError(f"Niepoprawny klucz wiadomości: {value!r}") from exc

    normalized_format = format_text.upper()
    normalized_kind = kind_text.casefold()
    if normalized_format not in {"STD", "EXT"}:
        raise ValueError(f"Niepoprawny format CAN w kluczu: {format_text!r}")
    if normalized_kind not in {"data", "remote", "error"}:
        raise ValueError(f"Niepoprawny typ ramki w kluczu: {kind_text!r}")
    maximum_id = 0x1FFFFFFF if normalized_format == "EXT" else 0x7FF
    if channel < 0 or not 0 <= arbitration_id <= maximum_id:
        raise ValueError(f"Niepoprawny klucz wiadomości: {value!r}")
    return TimelineMessageKey(
        channel=channel,
        arbitration_id=arbitration_id,
        is_extended_id=normalized_format == "EXT",
        frame_kind=normalized_kind,
    )


def format_timeline_message_key(key: TimelineMessageKey) -> str:
    frame_format = "EXT" if key.is_extended_id else "STD"
    return f"{key.channel}:{frame_format}:{key.arbitration_id:X}:{key.frame_kind}"


def frame_timeline_message_key(frame) -> str:
    if frame.is_error_frame:
        kind = "error"
    elif frame.is_remote_frame:
        kind = "remote"
    else:
        kind = "data"
    frame_format = "EXT" if frame.is_extended_id else "STD"
    return f"{frame.channel}:{frame_format}:{frame.arbitration_id:X}:{kind}"


def _build_lane(
    project: CrtProject,
    record: SessionRecord,
    *,
    synchronization_mode: str,
    anchor: TimelineMessageKey | None,
    max_events: int,
    should_cancel: Callable[[], bool] | None,
) -> ComparisonTimelineLane:
    reader = SessionPagedReader(project.absolute_path(record.relative_path))
    total = reader.frame_count
    stride = max(1, math.ceil(total / max_events)) if total else 1
    pending: list[_PendingEvent] = []
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    anchor_source_row: int | None = None
    anchor_timestamp: int | None = None

    for source_row, frame in enumerate(reader.iter_frames()):
        if source_row % _CANCEL_CHECK_INTERVAL == 0:
            _raise_if_cancelled(should_cancel)
        timestamp = int(frame.timestamp_ns)
        if first_timestamp is None:
            first_timestamp = timestamp
        last_timestamp = timestamp
        if synchronization_mode == SYNC_SESSION_START and anchor_timestamp is None:
            anchor_source_row = source_row
            anchor_timestamp = timestamp
        elif (
            synchronization_mode == SYNC_MESSAGE_KEY
            and anchor_timestamp is None
            and anchor is not None
            and _frame_matches(frame, anchor)
        ):
            anchor_source_row = source_row
            anchor_timestamp = timestamp

        if source_row % stride == 0:
            pending.append(
                _PendingEvent(
                    source_row=source_row,
                    sequence=int(frame.sequence),
                    timestamp_ns=timestamp,
                    message_key=frame_timeline_message_key(frame),
                    data_hex=frame.data_hex,
                    dlc=int(frame.dlc),
                )
            )

    _raise_if_cancelled(should_cancel)
    synchronized = anchor_timestamp is not None
    warning = ""
    if total == 0:
        warning = f"Sesja {record.name!r} nie zawiera ramek."
    elif not synchronized:
        assert anchor is not None
        warning = (
            f"Sesja {record.name!r} nie zawiera kotwicy "
            f"{format_timeline_message_key(anchor)}."
        )

    events = tuple(
        ComparisonTimelineEvent(
            session_id=record.id,
            session_name=record.name,
            source_row=item.source_row,
            sequence=item.sequence,
            timestamp_ns=item.timestamp_ns,
            relative_time_ns=(
                item.timestamp_ns - anchor_timestamp
                if anchor_timestamp is not None
                else None
            ),
            message_key=item.message_key,
            data_hex=item.data_hex,
            dlc=item.dlc,
        )
        for item in pending
    )
    return ComparisonTimelineLane(
        session_id=record.id,
        session_name=record.name,
        total_frame_count=total,
        sampled_frame_count=len(events),
        sample_stride=stride,
        anchor_source_row=anchor_source_row,
        anchor_timestamp_ns=anchor_timestamp,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        synchronized=synchronized,
        warning=warning,
        events=events,
    )


def _missing_lane(session_id: str, warning: str) -> ComparisonTimelineLane:
    return ComparisonTimelineLane(
        session_id=session_id,
        session_name=session_id,
        total_frame_count=0,
        sampled_frame_count=0,
        sample_stride=1,
        anchor_source_row=None,
        anchor_timestamp_ns=None,
        first_timestamp_ns=None,
        last_timestamp_ns=None,
        synchronized=False,
        warning=warning,
        events=(),
    )


def _frame_matches(frame, key: TimelineMessageKey) -> bool:
    if frame.channel != key.channel:
        return False
    if frame.arbitration_id != key.arbitration_id:
        return False
    if frame.is_extended_id != key.is_extended_id:
        return False
    if key.frame_kind == "error":
        return bool(frame.is_error_frame)
    if key.frame_kind == "remote":
        return bool(frame.is_remote_frame) and not frame.is_error_frame
    return not frame.is_remote_frame and not frame.is_error_frame


def _raise_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise ComparisonTimelineCancelled


__all__ = [
    "ComparisonTimelineCancelled",
    "ComparisonTimelineEvent",
    "ComparisonTimelineLane",
    "ComparisonTimelineResult",
    "DEFAULT_MAX_EVENTS_PER_SESSION",
    "SYNC_MESSAGE_KEY",
    "SYNC_SESSION_START",
    "build_comparison_timeline",
    "format_timeline_message_key",
    "frame_timeline_message_key",
    "parse_timeline_message_key",
]
