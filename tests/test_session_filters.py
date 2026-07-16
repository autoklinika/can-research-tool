from pathlib import Path

from app.filters import FilterMode, FilterPreset
from app.live_filters import ActiveFilterSet
from app.models import CanFrame, CaptureSession
from app.session_filters import load_filtered_session_page
from app.session_stream import SessionStreamWriter


def _write_session(path: Path) -> None:
    session = CaptureSession(name="stored", source="test")
    with SessionStreamWriter(session, path, index_stride=2) as writer:
        for sequence, can_id in enumerate((0x100, 0x101, 0x100, 0x102, 0x100)):
            writer.append(
                CanFrame(
                    sequence=sequence,
                    timestamp_ns=sequence * 1_000_000,
                    arbitration_id=can_id,
                    data=bytes([sequence]),
                )
            )


def test_saved_session_filter_scans_all_frames_but_retains_bounded_page(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stored.crt.jsonl"
    _write_session(path)

    preset = FilterPreset.create("Only 0x100")
    preset.mode = FilterMode.INCLUDE
    preset.root = {
        "type": "group",
        "operator": "and",
        "children": [
            {
                "type": "condition",
                "field": "can_id",
                "operator": "eq",
                "values": ["0x100"],
            }
        ],
    }

    page = load_filtered_session_page(
        path,
        ActiveFilterSet([preset]),
        max_rows=2,
    )

    assert page.total_frames == 5
    assert page.visible_frames == 3
    assert page.scanned_all_frames is True
    assert page.loaded_from_visible_index == 1
    assert [frame.sequence for frame in page.frames] == [2, 4]
    assert path.exists()


def test_saved_session_without_visibility_filter_uses_latest_indexed_page(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stored.crt.jsonl"
    _write_session(path)

    page = load_filtered_session_page(path, ActiveFilterSet(()), max_rows=2)

    assert page.total_frames == 5
    assert page.visible_frames == 5
    assert page.scanned_all_frames is False
    assert page.loaded_from_visible_index == 3
    assert [frame.sequence for frame in page.frames] == [3, 4]
