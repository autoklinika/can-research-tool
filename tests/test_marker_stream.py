from pathlib import Path

from app.marker_stream import MarkerStreamWriter, iter_markers
from app.markers import CaptureMarker, MarkerPreset


def test_marker_stream_round_trip(tmp_path: Path) -> None:
    preset = MarkerPreset.create("VGT ruch +", "F5", area="VGT")
    marker = CaptureMarker.from_preset(
        preset,
        12_345_678,
        source="keyboard",
    )
    path = tmp_path / "capture.markers.jsonl"

    with MarkerStreamWriter(path, presets=(preset,)) as writer:
        writer.append(marker)

    restored = list(iter_markers(path))
    assert restored == [marker]
