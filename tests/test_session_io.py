from pathlib import Path

from app.models import CanFrame, CaptureSession
from app.session_io import load_session, save_session


def test_session_round_trip(tmp_path: Path) -> None:
    session = CaptureSession(
        name="bench-change",
        source="kvaser-live",
        bitrate=250_000,
        channel=0,
        adapter="Kvaser Leaf",
        metadata={"mode": "silent"},
    )
    session.append(
        CanFrame(
            sequence=0,
            timestamp_ns=123,
            arbitration_id=0x18FF0011,
            data=bytes.fromhex("01 02 03"),
            is_extended_id=True,
            source_timestamp=456,
            source_flags=4,
        )
    )

    path = tmp_path / "capture.crt.jsonl"
    save_session(session, path)
    restored = load_session(path)

    assert restored.name == session.name
    assert restored.source == "kvaser-live"
    assert restored.metadata == {"mode": "silent"}
    assert restored.frames == session.frames
