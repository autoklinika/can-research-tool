from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from .models import CanFrame


@dataclass(frozen=True, slots=True)
class CanIdStatistics:
    arbitration_id: int
    is_extended_id: bool
    frame_count: int
    first_timestamp_ns: int
    last_timestamp_ns: int
    dlc_values: tuple[int, ...]
    unique_payloads: int
    mean_period_ms: float | None
    min_period_ms: float | None
    max_period_ms: float | None
    estimated_frequency_hz: float | None
    changing_byte_mask: tuple[bool, ...]


class SessionAnalyzer:
    """Protocol-neutral statistics for raw CAN frames."""

    def summarize(self, frames: Iterable[CanFrame]) -> list[CanIdStatistics]:
        grouped: dict[tuple[int, bool], list[CanFrame]] = defaultdict(list)
        for frame in frames:
            grouped[(frame.arbitration_id, frame.is_extended_id)].append(frame)

        summaries = [self._summarize_group(group) for group in grouped.values()]
        return sorted(summaries, key=lambda item: (item.is_extended_id, item.arbitration_id))

    @staticmethod
    def _summarize_group(frames: list[CanFrame]) -> CanIdStatistics:
        ordered = sorted(frames, key=lambda frame: (frame.timestamp_ns, frame.sequence))
        periods_ms = [
            (current.timestamp_ns - previous.timestamp_ns) / 1_000_000
            for previous, current in zip(ordered, ordered[1:])
            if current.timestamp_ns >= previous.timestamp_ns
        ]
        mean_period_ms = mean(periods_ms) if periods_ms else None
        frequency_hz = (
            1000.0 / mean_period_ms if mean_period_ms is not None and mean_period_ms > 0 else None
        )

        maximum_dlc = max((frame.dlc for frame in ordered), default=0)
        changing_mask = tuple(
            len({frame.data[index] for frame in ordered if index < frame.dlc}) > 1
            for index in range(maximum_dlc)
        )

        first = ordered[0]
        return CanIdStatistics(
            arbitration_id=first.arbitration_id,
            is_extended_id=first.is_extended_id,
            frame_count=len(ordered),
            first_timestamp_ns=ordered[0].timestamp_ns,
            last_timestamp_ns=ordered[-1].timestamp_ns,
            dlc_values=tuple(sorted({frame.dlc for frame in ordered})),
            unique_payloads=len({frame.data for frame in ordered}),
            mean_period_ms=mean_period_ms,
            min_period_ms=min(periods_ms) if periods_ms else None,
            max_period_ms=max(periods_ms) if periods_ms else None,
            estimated_frequency_hz=frequency_hz,
            changing_byte_mask=changing_mask,
        )
