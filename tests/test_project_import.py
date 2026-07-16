from pathlib import Path

from app.marker_stream import MarkerStreamWriter, iter_markers, marker_path_for_session
from app.markers import CaptureMarker, MarkerPreset
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter


def test_import_crt_session_copies_frames_and_markers(tmp_path: Path) -> None:
    source = tmp_path / "outside" / "bench.crt.jsonl"
    session = CaptureSession(name="bench", source="test")
    with SessionStreamWriter(session, source) as writer:
        writer.append(
            CanFrame(
                sequence=0,
                timestamp_ns=100,
                arbitration_id=0x123,
                data=b"\x01",
            )
        )

    preset = MarkerPreset.create("Zapłon ON", "F1")
    marker = CaptureMarker.from_preset(preset, 50, source="keyboard")
    with MarkerStreamWriter(marker_path_for_session(source), presets=(preset,)) as writer:
        writer.append(marker)

    project = CrtProject.create(tmp_path / "project", name="Import")
    record = project.import_log(source)
    imported = project.absolute_path(record.relative_path)

    assert imported.is_file()
    assert record.frame_count == 1
    assert record.marker_count == 1
    assert list(iter_markers(marker_path_for_session(imported))) == [marker]
