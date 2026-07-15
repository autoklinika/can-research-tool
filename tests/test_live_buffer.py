from app.live_buffer import LiveFrameBuffer
from app.models import CanFrame


def _frame(sequence: int) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=sequence * 1_000_000,
        arbitration_id=0x100 + sequence,
        data=bytes([sequence]),
    )


def test_live_buffer_is_bounded_and_reports_cursor_truncation() -> None:
    buffer = LiveFrameBuffer(capacity=3)
    buffer.append_many(_frame(sequence) for sequence in range(5))

    complete = buffer.snapshot_since(None)
    assert [frame.sequence for frame in complete.frames] == [2, 3, 4]
    assert complete.total_received == 5
    assert complete.dropped_from_view == 2
    assert complete.truncated is False

    stale_cursor = buffer.snapshot_since(0)
    assert stale_cursor.truncated is True
    assert [frame.sequence for frame in stale_cursor.frames] == [2, 3, 4]

    current_cursor = buffer.snapshot_since(3)
    assert current_cursor.truncated is False
    assert [frame.sequence for frame in current_cursor.frames] == [4]
