from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .filters import CanFrameRecord
from .live_filters import ActiveFilterSet
from .session_stream import SessionPagedReader
from .static_frame_adapter import static_frame_record


class StoredSearchNavigationCancelled(RuntimeError):
    """Raised when locating a source row is cancelled by a newer request."""


@dataclass(frozen=True, slots=True)
class StoredSearchLocation:
    """Location of one source row in the currently visible stored-session stream."""

    source_row: int
    total_frames: int
    visible: bool
    visible_index: int | None
    page_start: int | None
    local_row: int | None


def locate_stored_search_row(
    path: str | Path,
    filter_set,
    source_row: int,
    *,
    page_size: int,
    should_cancel: Callable[[], bool] | None = None,
) -> StoredSearchLocation:
    """Map a durable search-index row to one bounded stored-session page.

    The source row remains the zero-based raw frame position stored in the
    persistent search index. When visibility filters are active, only the
    prefix ending at the requested frame is scanned to calculate its visible
    position. No full frame collection is materialized.
    """

    requested = int(source_row)
    if requested < 0:
        raise ValueError("source_row cannot be negative")
    if page_size <= 0:
        raise ValueError("page_size must be greater than zero")

    reader = SessionPagedReader(path)
    total_frames = reader.frame_count
    if requested >= total_frames:
        raise IndexError(
            f"source_row {requested} is outside the stored session "
            f"with {total_frames} frames"
        )

    if should_cancel is not None and should_cancel():
        raise StoredSearchNavigationCancelled()

    if not filter_set.affects_visibility:
        page_start = (requested // page_size) * page_size
        return StoredSearchLocation(
            source_row=requested,
            total_frames=total_frames,
            visible=True,
            visible_index=requested,
            page_start=page_start,
            local_row=requested - page_start,
        )

    visible_index = 0
    for current_row, frame in enumerate(reader.iter_frames(limit=requested + 1)):
        if should_cancel is not None and current_row % 1024 == 0 and should_cancel():
            raise StoredSearchNavigationCancelled()

        visible = filter_set.decide(_frame_record(frame, filter_set)).visible
        if current_row == requested:
            if not visible:
                return StoredSearchLocation(
                    source_row=requested,
                    total_frames=total_frames,
                    visible=False,
                    visible_index=None,
                    page_start=None,
                    local_row=None,
                )
            page_start = (visible_index // page_size) * page_size
            return StoredSearchLocation(
                source_row=requested,
                total_frames=total_frames,
                visible=True,
                visible_index=visible_index,
                page_start=page_start,
                local_row=visible_index - page_start,
            )
        if visible:
            visible_index += 1

    raise IndexError(f"source_row {requested} could not be located")


def _frame_record(frame, filter_set):
    """Preserve the same evaluator boundary as stored-session pagination."""

    if isinstance(filter_set, ActiveFilterSet):
        return CanFrameRecord(
            can_id=int(frame.arbitration_id),
            extended=bool(frame.is_extended_id),
            dlc=int(frame.dlc),
            relative_time_us=int(frame.timestamp_ns // 1_000),
            channel=int(frame.channel),
        )
    return static_frame_record(frame)
