from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .analysis import CanIdStatistics
from .models import CanFrame


def save_frames_csv(frames: Iterable[CanFrame], path: str | Path) -> None:
    """Export raw frames in a human-readable, Kvaser-friendly CSV format."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(
            [
                "timestamp_ms",
                "sequence",
                "can_id",
                "type",
                "dlc",
                "data",
                "channel",
                "remote",
                "error",
                "source_timestamp",
                "source_flags",
            ]
        )

        for frame in frames:
            id_width = 8 if frame.is_extended_id else 3
            writer.writerow(
                [
                    f"{frame.timestamp_ns / 1_000_000:.6f}",
                    frame.sequence,
                    f"{frame.arbitration_id:0{id_width}X}",
                    "EXT" if frame.is_extended_id else "STD",
                    frame.dlc,
                    frame.data_hex,
                    frame.channel,
                    "yes" if frame.is_remote_frame else "no",
                    "yes" if frame.is_error_frame else "no",
                    "" if frame.source_timestamp is None else frame.source_timestamp,
                    frame.source_flags,
                ]
            )


def save_summary_csv(statistics: Iterable[CanIdStatistics], path: str | Path) -> None:
    """Export protocol-neutral statistics grouped by CAN ID."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(
            [
                "can_id",
                "type",
                "frame_count",
                "dlc_values",
                "unique_payloads",
                "mean_period_ms",
                "min_period_ms",
                "max_period_ms",
                "estimated_frequency_hz",
                "changing_bytes",
                "first_timestamp_ms",
                "last_timestamp_ms",
            ]
        )

        for item in statistics:
            id_width = 8 if item.is_extended_id else 3
            changing_bytes = ",".join(
                str(index) for index, is_changing in enumerate(item.changing_byte_mask) if is_changing
            )
            writer.writerow(
                [
                    f"{item.arbitration_id:0{id_width}X}",
                    "EXT" if item.is_extended_id else "STD",
                    item.frame_count,
                    ",".join(str(value) for value in item.dlc_values),
                    item.unique_payloads,
                    _format_optional(item.mean_period_ms),
                    _format_optional(item.min_period_ms),
                    _format_optional(item.max_period_ms),
                    _format_optional(item.estimated_frequency_hz),
                    changing_bytes,
                    f"{item.first_timestamp_ns / 1_000_000:.6f}",
                    f"{item.last_timestamp_ns / 1_000_000:.6f}",
                ]
            )


def _format_optional(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"
