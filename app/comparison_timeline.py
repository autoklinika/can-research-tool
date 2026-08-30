from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .domain import ComparisonSet
from .marker_stream import iter_markers, marker_path_for_session
from .markers import CaptureMarker
from .project import CrtProject, SessionRecord
from .session_stream import SessionPagedReader

SYNC_SESSION_START = "session_start"
SYNC_MESSAGE_KEY = "message_key"
SYNC_OPERATOR_MARKER = "operator_marker"
SYNC_EXPLICIT_EVENT = "explicit_event"
DEFAULT_MAX_EVENTS_PER_SESSION = 2_000
_CANCEL_CHECK_INTERVAL = 1_024
_SUPPORTED_SYNCHRONIZATION_MODES = {
    SYNC_SESSION_START,
    SYNC_MESSAGE_KEY,
    SYNC_OPERATOR_MARKER,
    SYNC_EXPLICIT_EVENT,
}


class ComparisonTimelineCancelled(RuntimeError):
    """Raised when timeline construction is cancelled."""


@dataclass(frozen=True, slots=True)
class TimelineMessageKey:
    channel: int
    arbitration_id: int
    is_extended_id: bool
    frame_kind: str


@dataclass(frozen=True, slots=True)
class TimelineAnchorConfiguration:
    synchronization_mode: str = SYNC_SESSION_START
    anchor_message_key: str = ""
    anchor_marker_name: str = ""
    anchor_occurrence: int = 1
    explicit_anchor_rows: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if self.synchronization_mode not in _SUPPORTED_SYNCHRONIZATION_MODES:
            raise ValueError(
                f"Nieobsługiwany tryb synchronizacji: {self.synchronization_mode!r}"
            )
        if self.anchor_occurrence <= 0:
            raise ValueError("anchor_occurrence must be greater than zero")
        seen: set[str] = set()
        for session_id, source_row in self.explicit_anchor_rows:
            if not str(session_id).strip():
                raise ValueError("explicit anchor session_id cannot be empty")
            if session_id in seen:
                raise ValueError("explicit anchor session_ids must be unique")
            if int(source_row) < 0:
                raise ValueError("explicit anchor source_row cannot be negative")
            seen.add(session_id)

    @property
    def explicit_rows(self) -> dict[str, int]:
        return {
            session_id: int(source_row)
            for session_id, source_row in self.explicit_anchor_rows
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "synchronization_mode": self.synchronization_mode,
            "anchor_message_key": self.anchor_message_key,
            "anchor_marker_name": self.anchor_marker_name,
            "anchor_occurrence": self.anchor_occurrence,
            "explicit_anchor_rows": {
                session_id: source_row
                for session_id, source_row in self.explicit_anchor_rows
            },
        }


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
    anchor_kind: str = ""
    anchor_label: str = ""
    anchor_reference: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ComparisonTimelineResult:
    synchronization_mode: str
    anchor_message_key: str
    lanes: tuple[ComparisonTimelineLane, ...]
    warnings: tuple[str, ...]
    minimum_relative_time_ns: int
    maximum_relative_time_ns: int
    anchor_marker_name: str = ""
    anchor_occurrence: int = 1
    explicit_anchor_rows: tuple[tuple[str, int], ...] = ()

    @property
    def configuration(self) -> TimelineAnchorConfiguration:
        return TimelineAnchorConfiguration(
            synchronization_mode=self.synchronization_mode,
            anchor_message_key=self.anchor_message_key,
            anchor_marker_name=self.anchor_marker_name,
            anchor_occurrence=self.anchor_occurrence,
            explicit_anchor_rows=self.explicit_anchor_rows,
        )


@dataclass(frozen=True, slots=True)
class _PendingEvent:
    source_row: int
    sequence: int
    timestamp_ns: int
    message_key: str
    data_hex: str
    dlc: int


@dataclass(frozen=True, slots=True)
class _MarkerAnchor:
    marker: CaptureMarker
    occurrence: int


def build_comparison_timeline(
    project: CrtProject,
    comparison_set: ComparisonSet,
    *,
    synchronization_mode: str = SYNC_SESSION_START,
    anchor_message_key: str = "",
    anchor_marker_name: str = "",
    anchor_occurrence: int = 1,
    explicit_anchor_rows: Mapping[str, int] | None = None,
    max_events_per_session: int = DEFAULT_MAX_EVENTS_PER_SESSION,
    should_cancel: Callable[[], bool] | None = None,
) -> ComparisonTimelineResult:
    """Build a bounded, passive timeline without modifying source sessions."""

    configuration = normalize_timeline_configuration(
        synchronization_mode=synchronization_mode,
        anchor_message_key=anchor_message_key,
        anchor_marker_name=anchor_marker_name,
        anchor_occurrence=anchor_occurrence,
        explicit_anchor_rows=explicit_anchor_rows,
    )
    if max_events_per_session < 3:
        raise ValueError("max_events_per_session must be at least three")

    parsed_anchor = (
        parse_timeline_message_key(configuration.anchor_message_key)
        if configuration.synchronization_mode == SYNC_MESSAGE_KEY
        else None
    )
    explicit_rows = configuration.explicit_rows
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
            lanes.append(
                _missing_lane(
                    session_id,
                    warning,
                    configuration.synchronization_mode,
                )
            )
            continue

        marker_anchor = None
        if configuration.synchronization_mode == SYNC_OPERATOR_MARKER:
            marker_anchor = _find_marker_anchor(
                project,
                record,
                configuration.anchor_marker_name,
                configuration.anchor_occurrence,
                should_cancel,
            )
        lane = _build_lane(
            project,
            record,
            synchronization_mode=configuration.synchronization_mode,
            message_anchor=parsed_anchor,
            marker_anchor=marker_anchor,
            requested_marker_name=configuration.anchor_marker_name,
            anchor_occurrence=configuration.anchor_occurrence,
            explicit_anchor_row=explicit_rows.get(record.id),
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
        synchronization_mode=configuration.synchronization_mode,
        anchor_message_key=configuration.anchor_message_key,
        anchor_marker_name=configuration.anchor_marker_name,
        anchor_occurrence=configuration.anchor_occurrence,
        explicit_anchor_rows=configuration.explicit_anchor_rows,
        lanes=tuple(lanes),
        warnings=tuple(warnings),
        minimum_relative_time_ns=minimum,
        maximum_relative_time_ns=maximum,
    )


def normalize_timeline_configuration(
    *,
    synchronization_mode: str,
    anchor_message_key: str = "",
    anchor_marker_name: str = "",
    anchor_occurrence: int = 1,
    explicit_anchor_rows: Mapping[str, int] | None = None,
) -> TimelineAnchorConfiguration:
    mode = str(synchronization_mode).strip()
    occurrence = int(anchor_occurrence)
    message_key = str(anchor_message_key).strip()
    marker_name = str(anchor_marker_name).strip()
    rows = tuple(
        sorted(
            (
                (str(session_id).strip(), int(source_row))
                for session_id, source_row in dict(
                    explicit_anchor_rows or {}
                ).items()
            ),
            key=lambda item: item[0],
        )
    )
    if mode == SYNC_MESSAGE_KEY:
        if not message_key:
            raise ValueError(
                "Podaj klucz wiadomości używany jako kotwica synchronizacji."
            )
        message_key = format_timeline_message_key(
            parse_timeline_message_key(message_key)
        )
    elif mode == SYNC_OPERATOR_MARKER:
        if not marker_name:
            raise ValueError("Podaj dokładną nazwę znacznika operatora.")
    elif mode == SYNC_EXPLICIT_EVENT and not rows:
        raise ValueError("Ustaw co najmniej jedną dokładną kotwicę zdarzenia.")
    return TimelineAnchorConfiguration(
        synchronization_mode=mode,
        anchor_message_key=message_key,
        anchor_marker_name=marker_name,
        anchor_occurrence=occurrence,
        explicit_anchor_rows=rows,
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


def _find_marker_anchor(
    project: CrtProject,
    record: SessionRecord,
    marker_name: str,
    occurrence: int,
    should_cancel: Callable[[], bool] | None,
) -> _MarkerAnchor | None:
    session_path = project.absolute_path(record.relative_path)
    marker_path = marker_path_for_session(session_path)
    matched = 0
    for index, marker in enumerate(iter_markers(marker_path)):
        if index % 128 == 0:
            _raise_if_cancelled(should_cancel)
        if marker.name.casefold() != marker_name.casefold():
            continue
        matched += 1
        if matched == occurrence:
            return _MarkerAnchor(marker=marker, occurrence=occurrence)
    return None


def _build_lane(
    project: CrtProject,
    record: SessionRecord,
    *,
    synchronization_mode: str,
    message_anchor: TimelineMessageKey | None,
    marker_anchor: _MarkerAnchor | None,
    requested_marker_name: str,
    anchor_occurrence: int,
    explicit_anchor_row: int | None,
    max_events: int,
    should_cancel: Callable[[], bool] | None,
) -> ComparisonTimelineLane:
    reader = SessionPagedReader(project.absolute_path(record.relative_path))
    total = reader.frame_count
    sample_rows = _sample_source_rows(total, max_events)
    stride = _display_sample_stride(total, max_events)
    pending: list[_PendingEvent] = []
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    anchor_source_row: int | None = None
    anchor_timestamp: int | None = None
    anchor_event: _PendingEvent | None = None
    anchor_kind = synchronization_mode
    anchor_label = ""
    anchor_reference: dict[str, Any] = {}
    message_match_count = 0
    nearest_marker_delta: int | None = None

    if synchronization_mode == SYNC_OPERATOR_MARKER and marker_anchor is not None:
        anchor_timestamp = int(marker_anchor.marker.timestamp_ns)
        anchor_label = marker_anchor.marker.name
        anchor_reference = {
            "marker_id": marker_anchor.marker.id,
            "marker_preset_id": marker_anchor.marker.preset_id,
            "marker_name": marker_anchor.marker.name,
            "marker_note": marker_anchor.marker.note,
            "marker_area": marker_anchor.marker.area,
            "occurrence": marker_anchor.occurrence,
        }

    for source_row, frame in enumerate(reader.iter_frames()):
        if source_row % _CANCEL_CHECK_INTERVAL == 0:
            _raise_if_cancelled(should_cancel)
        timestamp = int(frame.timestamp_ns)
        if first_timestamp is None:
            first_timestamp = timestamp
        last_timestamp = timestamp
        event = _pending_event(source_row, frame)

        if synchronization_mode == SYNC_SESSION_START and anchor_timestamp is None:
            anchor_source_row = source_row
            anchor_timestamp = timestamp
            anchor_event = event
            anchor_label = "Początek sesji"
            anchor_reference = {"source_row": source_row}
        elif synchronization_mode == SYNC_MESSAGE_KEY and message_anchor is not None:
            if _frame_matches(frame, message_anchor):
                message_match_count += 1
                if (
                    message_match_count == anchor_occurrence
                    and anchor_timestamp is None
                ):
                    anchor_source_row = source_row
                    anchor_timestamp = timestamp
                    anchor_event = event
                    anchor_label = format_timeline_message_key(message_anchor)
                    anchor_reference = {
                        "message_key": anchor_label,
                        "occurrence": anchor_occurrence,
                        "source_row": source_row,
                    }
        elif synchronization_mode == SYNC_EXPLICIT_EVENT:
            if (
                explicit_anchor_row is not None
                and source_row == explicit_anchor_row
            ):
                anchor_source_row = source_row
                anchor_timestamp = timestamp
                anchor_event = event
                anchor_label = f"Ramka {source_row + 1}"
                anchor_reference = {
                    "source_row": source_row,
                    "message_key": event.message_key,
                    "sequence": event.sequence,
                }
        elif (
            synchronization_mode == SYNC_OPERATOR_MARKER
            and marker_anchor is not None
        ):
            delta = abs(timestamp - marker_anchor.marker.timestamp_ns)
            if nearest_marker_delta is None or delta < nearest_marker_delta:
                nearest_marker_delta = delta
                anchor_source_row = source_row
                anchor_event = event
                anchor_reference["source_row"] = source_row
                anchor_reference["nearest_frame_timestamp_ns"] = timestamp

        if source_row in sample_rows:
            pending.append(event)

    _raise_if_cancelled(should_cancel)
    _retain_anchor_event(
        pending,
        anchor_event,
        max_events=max_events,
        total_frame_count=total,
    )

    synchronized = anchor_timestamp is not None and anchor_source_row is not None
    warning = _lane_warning(
        record,
        synchronization_mode=synchronization_mode,
        total=total,
        synchronized=synchronized,
        message_anchor=message_anchor,
        marker_name=marker_anchor.marker.name if marker_anchor is not None else "",
        requested_marker_name=requested_marker_name,
        anchor_occurrence=anchor_occurrence,
        explicit_anchor_row=explicit_anchor_row,
    )
    if synchronization_mode == SYNC_OPERATOR_MARKER and marker_anchor is None:
        warning = (
            f"Sesja {record.name!r} nie zawiera wystąpienia nr "
            f"{anchor_occurrence} znacznika {requested_marker_name!r}."
        )
        anchor_label = ""
        anchor_reference = {"occurrence": anchor_occurrence}
    elif synchronization_mode == SYNC_OPERATOR_MARKER and total == 0:
        synchronized = False
        warning = (
            f"Sesja {record.name!r} zawiera znacznik, ale nie zawiera ramek."
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
                if synchronized and anchor_timestamp is not None
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
        anchor_kind=anchor_kind,
        anchor_label=anchor_label,
        anchor_reference=anchor_reference,
    )


def _lane_warning(
    record: SessionRecord,
    *,
    synchronization_mode: str,
    total: int,
    synchronized: bool,
    message_anchor: TimelineMessageKey | None,
    marker_name: str,
    requested_marker_name: str,
    anchor_occurrence: int,
    explicit_anchor_row: int | None,
) -> str:
    if total == 0:
        return f"Sesja {record.name!r} nie zawiera ramek."
    if synchronized:
        return ""
    if synchronization_mode == SYNC_MESSAGE_KEY and message_anchor is not None:
        return (
            f"Sesja {record.name!r} nie zawiera wystąpienia nr "
            f"{anchor_occurrence} kotwicy "
            f"{format_timeline_message_key(message_anchor)}."
        )
    if synchronization_mode == SYNC_OPERATOR_MARKER:
        name = marker_name or requested_marker_name or "podanej nazwy"
        return (
            f"Sesja {record.name!r} nie zawiera wystąpienia nr "
            f"{anchor_occurrence} znacznika {name!r}."
        )
    if synchronization_mode == SYNC_EXPLICIT_EVENT:
        if explicit_anchor_row is None:
            return (
                f"Dla sesji {record.name!r} nie ustawiono dokładnej "
                "kotwicy zdarzenia."
            )
        return (
            f"Kotwica wiersza {explicit_anchor_row + 1} wykracza poza "
            f"sesję {record.name!r}."
        )
    return f"Nie udało się zsynchronizować sesji {record.name!r}."


def _pending_event(source_row: int, frame) -> _PendingEvent:
    return _PendingEvent(
        source_row=source_row,
        sequence=int(frame.sequence),
        timestamp_ns=int(frame.timestamp_ns),
        message_key=frame_timeline_message_key(frame),
        data_hex=frame.data_hex,
        dlc=int(frame.dlc),
    )


def _sample_source_rows(total: int, max_events: int) -> set[int]:
    if total <= 0:
        return set()
    if total <= max_events:
        return set(range(total))
    denominator = max_events - 1
    return {
        (index * (total - 1) + denominator // 2) // denominator
        for index in range(max_events)
    }


def _display_sample_stride(total: int, max_events: int) -> int:
    if total <= 1 or total <= max_events:
        return 1
    return max(1, round((total - 1) / (max_events - 1)))


def _retain_anchor_event(
    pending: list[_PendingEvent],
    anchor_event: _PendingEvent | None,
    *,
    max_events: int,
    total_frame_count: int,
) -> None:
    if anchor_event is None:
        return
    if any(item.source_row == anchor_event.source_row for item in pending):
        return
    if len(pending) < max_events:
        pending.append(anchor_event)
    else:
        endpoint_rows = {0, max(0, total_frame_count - 1)}
        candidates = [
            index
            for index, item in enumerate(pending)
            if item.source_row not in endpoint_rows
        ]
        if not candidates:
            raise RuntimeError("bounded timeline has no replaceable interior sample")
        replacement_index = min(
            candidates,
            key=lambda index: (
                abs(pending[index].source_row - anchor_event.source_row),
                -pending[index].source_row,
            ),
        )
        pending[replacement_index] = anchor_event
    pending.sort(key=lambda item: item.source_row)


def _missing_lane(
    session_id: str,
    warning: str,
    synchronization_mode: str,
) -> ComparisonTimelineLane:
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
        anchor_kind=synchronization_mode,
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
    "SYNC_EXPLICIT_EVENT",
    "SYNC_MESSAGE_KEY",
    "SYNC_OPERATOR_MARKER",
    "SYNC_SESSION_START",
    "TimelineAnchorConfiguration",
    "build_comparison_timeline",
    "format_timeline_message_key",
    "frame_timeline_message_key",
    "normalize_timeline_configuration",
    "parse_timeline_message_key",
]
