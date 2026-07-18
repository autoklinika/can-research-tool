from __future__ import annotations

import os

from .live_capture import LiveCaptureWidget

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
STAGE_H_FRAME_CAPACITY = 20_000
STAGE_H_MESSAGE_CAPACITY = 5_000


class StageHLiveCaptureWidget(LiveCaptureWidget):
    """Temporary bounded-preview variant used only during Stage H measurements.

    The full capture and raw persistence path remain unchanged. Only the two GUI-facing
    bounded buffers and table models receive the smaller capacities already documented
    by CRT for normal Live preview operation.
    """

    LIVE_CAPACITY = STAGE_H_FRAME_CAPACITY
    LIVE_MESSAGE_CAPACITY = STAGE_H_MESSAGE_CAPACITY


def live_capture_widget_type() -> type[LiveCaptureWidget]:
    """Return the measurement widget only when Stage H diagnostics are enabled."""

    enabled = os.getenv("CRT_LIVE_PERF", "").strip().casefold() in _TRUE_VALUES
    return StageHLiveCaptureWidget if enabled else LiveCaptureWidget
