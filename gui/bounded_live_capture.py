from __future__ import annotations

from .live_capture import LiveCaptureWidget

LIVE_PREVIEW_FRAME_CAPACITY = 20_000
LIVE_PREVIEW_MESSAGE_CAPACITY = 5_000


class BoundedLiveCaptureWidget(LiveCaptureWidget):
    """Production Live Capture view with bounded presentation buffers.

    The limits apply only to the GUI-facing preview and the matching controller
    snapshots. Full raw-frame persistence and logical-message exports remain
    unchanged and continue for the entire capture session.
    """

    LIVE_CAPACITY = LIVE_PREVIEW_FRAME_CAPACITY
    LIVE_MESSAGE_CAPACITY = LIVE_PREVIEW_MESSAGE_CAPACITY
