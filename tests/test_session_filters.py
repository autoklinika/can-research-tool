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


def _only_100_filter() -> ActiveFilterSet:
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
    return ActiveFilterSet([preset])


def test_saved_session_filter_loads_first_bounded_page(tmp_path: Path) -> None:
    path = tmp_path / "stored.crt.jsonl"
    _write_session(path)

    page = load_filtered_session_page(
        path,
        _only_100_filter(),
        max_rows=2,
    )

    assert page.total_frames == 5
    assert page.visible_frames == 3
    assert page.scanned_all_frames is True
    assert page.loaded_from_visible_index == 0
    assert [frame.sequence for frame in page.frames] == [0, 2]
    assert path.exists()


def test_saved_session_filter_can_load_next_result_page(tmp_path: Path) -> None:
    path = tmp_path / "stored.crt.jsonl"
    _write_session(path)

    page = load_filtered_session_page(
        path,
        _only_100_filter(),
        max_rows=2,
        start=2,
    )

    assert page.visible_frames == 3
    assert page.loaded_from_visible_index == 2
    assert [frame.sequence for frame in page.frames] == [4]


def test_saved_session_without_visibility_filter_uses_requested_indexed_page(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stored.crt.jsonl"
    _write_session(path)

    first = load_filtered_session_page(path, ActiveFilterSet(()), max_rows=2)
    last = load_filtered_session_page(path, ActiveFilterSet(()), max_rows=2, start=4)

    assert first.total_frames == 5
    assert first.visible_frames == 5
    assert first.scanned_all_frames is False
    assert first.loaded_from_visible_index == 0
    assert [frame.sequence for frame in first.frames] == [0, 1]

    assert last.loaded_from_visible_index == 4
    assert [frame.sequence for frame in last.frames] == [4]


def test_saved_session_page_start_is_clamped_to_last_page(tmp_path: Path) -> None:
    path = tmp_path / "stored.crt.jsonl"
    _write_session(path)

    page = load_filtered_session_page(
        path,
        ActiveFilterSet(()),
        max_rows=2,
        start=999,
    )

    assert page.loaded_from_visible_index == 4
    assert [frame.sequence for frame in page.frames] == [4]
