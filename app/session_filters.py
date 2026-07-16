from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .filters import CanFrameRecord
from .live_filters import ActiveFilterSet
from .models import CanFrame
from .session_stream import SessionPagedReader


@dataclass(frozen=True, slots=True)
class FilteredSessionPage:
    frames: tuple[CanFrame, ...]
    total_frames: int
    visible_frames: int
    loaded_from_visible_index: int
    scanned_all_frames: bool


def load_filtered_session_page(
    path: str | Path,
    filter_set: ActiveFilterSet,
    *,
    max_rows: int,
    start: int = 0,
) -> FilteredSessionPage:
    """Load one deterministic page from a stored session.

    Without Include/Exclude presets the sparse session index reads the requested
    source range directly. With visibility filters active the file is scanned in a
    worker thread and only the requested range of matching frames is retained.

    The default page starts at frame zero. This avoids silently presenting the last
    GUI-sized window as though it were the complete session.
    """

    if max_rows <= 0:
        raise ValueError("max_rows must be greater than zero")
    if start < 0:
        raise ValueError("start cannot be negative")

    reader = SessionPagedReader(path)
    total_frames = reader.frame_count

    if not filter_set.affects_visibility:
        page_start = _clamp_page_start(start, total_frames, max_rows)
        frames = tuple(reader.read_page(page_start, max_rows))
        return FilteredSessionPage(
            frames=frames,
            total_frames=total_frames,
            visible_frames=total_frames,
            loaded_from_visible_index=page_start,
            scanned_all_frames=False,
        )

    page_start = start
    frames, visible_count = _scan_filtered_range(
        reader,
        filter_set,
        start=page_start,
        max_rows=max_rows,
    )
    clamped_start = _clamp_page_start(page_start, visible_count, max_rows)
    if clamped_start != page_start:
        frames, visible_count = _scan_filtered_range(
            reader,
            filter_set,
            start=clamped_start,
            max_rows=max_rows,
        )

    return FilteredSessionPage(
        frames=tuple(frames),
        total_frames=total_frames,
        visible_frames=visible_count,
        loaded_from_visible_index=clamped_start,
        scanned_all_frames=True,
    )


def _scan_filtered_range(
    reader: SessionPagedReader,
    filter_set: ActiveFilterSet,
    *,
    start: int,
    max_rows: int,
) -> tuple[list[CanFrame], int]:
    selected: list[CanFrame] = []
    visible_count = 0
    end = start + max_rows

    for frame in reader.iter_frames():
        decision = filter_set.decide(
            CanFrameRecord(
                can_id=int(frame.arbitration_id),
                extended=bool(frame.is_extended_id),
                dlc=int(frame.dlc),
                relative_time_us=int(frame.timestamp_ns // 1_000),
                channel=int(frame.channel),
            )
        )
        if not decision.visible:
            continue
        if start <= visible_count < end:
            selected.append(frame)
        visible_count += 1

    return selected, visible_count


def _clamp_page_start(start: int, total: int, page_size: int) -> int:
    if total <= 0:
        return 0
    last_page_start = ((total - 1) // page_size) * page_size
    return min(start, last_page_start)
