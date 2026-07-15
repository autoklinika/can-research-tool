from pathlib import Path

from app.analysis import SessionAnalyzer
from app.exports import save_frames_csv, save_summary_csv
from app.models import CanFrame


def test_exports_raw_frames_and_summary(tmp_path: Path) -> None:
    frames = [
        CanFrame(
            sequence=0,
            timestamp_ns=0,
            arbitration_id=0x123,
            data=bytes.fromhex("10 20"),
        ),
        CanFrame(
            sequence=1,
            timestamp_ns=100_000_000,
            arbitration_id=0x123,
            data=bytes.fromhex("10 21"),
        ),
        CanFrame(
            sequence=2,
            timestamp_ns=200_000_000,
            arbitration_id=0x18FEAE30,
            data=bytes.fromhex("FF FF 00 00 FF FF FF FF"),
            is_extended_id=True,
        ),
    ]

    frames_path = tmp_path / "capture.frames.csv"
    summary_path = tmp_path / "capture.summary.csv"

    save_frames_csv(frames, frames_path)
    save_summary_csv(SessionAnalyzer().summarize(frames), summary_path)

    frames_text = frames_path.read_text(encoding="utf-8-sig")
    summary_text = summary_path.read_text(encoding="utf-8-sig")

    assert "timestamp_ms;sequence;can_id;type;dlc;data" in frames_text
    assert "0.000000;0;123;STD;2;10 20" in frames_text
    assert "200.000000;2;18FEAE30;EXT;8;FF FF 00 00 FF FF FF FF" in frames_text

    assert "can_id;type;frame_count" in summary_text
    assert "123;STD;2;2;2;100.000000" in summary_text
    assert "18FEAE30;EXT;1;8;1" in summary_text
