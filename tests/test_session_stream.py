from pathlib import Path

from app.models import CanFrame, CaptureSession
from app.session_io import load_session
from app.session_stream import (
    SessionPagedReader,
    SessionStreamWriter,
    iter_session_frames,
    read_session_header,
)


def test_streaming_session_supports_sequential_and_paged_reads(tmp_path: Path) -> None:
    session = CaptureSession(
        name="large-capture",
        source="test",
        bitrate=250_000,
        channel=0,
        adapter="Fake Kvaser",
    )
    path = tmp_path / "large.crt.jsonl"

    with SessionStreamWriter(session, path, flush_every=2, index_stride=2) as writer:
        for sequence in range(5):
            writer.append(
                CanFrame(
                    sequence=sequence,
                    timestamp_ns=sequence * 10_000_000,
                    arbitration_id=0x18FF0000 + sequence,
                    data=bytes([sequence, 0xAA]),
                    is_extended_id=True,
                )
            )

    header = read_session_header(path)
    assert header.name == "large-capture"
    assert header.frames == []

    sequential = list(iter_session_frames(path))
    assert [frame.sequence for frame in sequential] == [0, 1, 2, 3, 4]

    reader = SessionPagedReader(path, index_stride=2)
    assert reader.frame_count == 5
    page = reader.read_page(2, 2)
    assert [frame.sequence for frame in page] == [2, 3]
    assert reader.index_path.exists()

    restored = load_session(path)
    assert restored.frames == sequential
