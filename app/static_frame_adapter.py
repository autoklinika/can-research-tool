from __future__ import annotations

from .models import CanFrame
from .static_filter_engine import StaticCanFrameRecord


def static_frame_record(frame: CanFrame) -> StaticCanFrameRecord:
    """Convert the application's canonical frame without dropping v2 filter fields."""

    return StaticCanFrameRecord(
        can_id=int(frame.arbitration_id),
        extended=bool(frame.is_extended_id),
        dlc=int(frame.dlc),
        relative_time_us=int(frame.timestamp_ns // 1_000),
        channel=int(frame.channel),
        rtr=bool(frame.is_remote_frame),
        error_frame=bool(frame.is_error_frame),
        payload=bytes(frame.data),
    )
