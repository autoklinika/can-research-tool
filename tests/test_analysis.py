from app.analysis import SessionAnalyzer
from app.models import CanFrame


def test_summarizes_periodicity_and_byte_changes() -> None:
    frames = [
        CanFrame(0, 0, 0x123, bytes.fromhex("10 20")),
        CanFrame(1, 100_000_000, 0x123, bytes.fromhex("10 21")),
        CanFrame(2, 200_000_000, 0x123, bytes.fromhex("10 22")),
    ]

    summary = SessionAnalyzer().summarize(frames)

    assert len(summary) == 1
    item = summary[0]
    assert item.frame_count == 3
    assert item.dlc_values == (2,)
    assert item.unique_payloads == 3
    assert item.mean_period_ms == 100.0
    assert item.estimated_frequency_hz == 10.0
    assert item.changing_byte_mask == (False, True)
