from __future__ import annotations

from collections import deque
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
) -> FilteredSessionPage:
    """Return the newest visible frames without loading the full session into RAM.

    With no Include/Exclude preset, the sparse session index is used to fetch only
    the newest page. When visibility filters are active, the file is scanned in a
    worker thread and only the newest ``max_rows`` matching frames are retained.
    The scan is intentionally linear until Stage 9 introduces index-assisted
    predicate planning.
    """

    if max_rows <= 0:
        raise ValueError("max_rows must be greater than zero")

    reader = SessionPagedReader(path)
    total_frames = reader.frame_count

    if not filter_set.affects_visibility:
        start = max(0, total_frames - max_rows)
        frames = tuple(reader.read_page(start, max_rows))
        return FilteredSessionPage(
            frames=frames,
            total_frames=total_frames,
            visible_frames=total_frames,
            loaded_from_visible_index=start,
            scanned_all_frames=False,
        )

    retained: deque[CanFrame] = deque(maxlen=max_rows)
    visible_count = 0
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
        if decision.visible:
            retained.append(frame)
            visible_count += 1

    return FilteredSessionPage(
        frames=tuple(retained),
        total_frames=total_frames,
        visible_frames=visible_count,
        loaded_from_visible_index=max(0, visible_count - len(retained)),
        scanned_all_frames=True,
    )
