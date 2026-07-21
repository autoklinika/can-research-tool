from __future__ import annotations

from pathlib import Path

from app.filters import FilterMode, FilterPreset
from app.live_filters import ActiveFilterSet
from app.models import CanFrame, CaptureSession
from app.session_stream import SessionStreamWriter
from app.stored_search_navigation import locate_stored_search_row


def _write_session(path: Path) -> None:
    with SessionStreamWriter(
        CaptureSession(name="navigation", source="test"),
        path,
        index_stride=2,
    ) as writer:
        for sequence, can_id in enumerate((0x100, 0x101, 0x100, 0x102, 0x100)):
            writer.append(
                CanFrame(
                    sequence=sequence,
                    timestamp_ns=sequence * 1_000_000,
                    arbitration_id=can_id,
                    data=bytes((0xA0, sequence)),
                )
            )


def _only_100_filter() -> ActiveFilterSet:
    preset = FilterPreset.create("Only 0x100")
    preset.enabled = True
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
    return ActiveFilterSet((preset,), scope="stored_session")


def test_unfiltered_source_row_maps_directly_to_bounded_page(tmp_path: Path) -> None:
    path = tmp_path / "stored.crt.jsonl"
    _write_session(path)

    location = locate_stored_search_row(
        path,
        ActiveFilterSet((), scope="stored_session"),
        4,
        page_size=2,
    )

    assert location.visible is True
    assert location.visible_index == 4
    assert location.page_start == 4
    assert location.local_row == 0
    assert location.total_frames == 5


def test_filtered_source_row_maps_to_visible_page_and_local_row(tmp_path: Path) -> None:
    path = tmp_path / "stored.crt.jsonl"
    _write_session(path)

    location = locate_stored_search_row(
        path,
        _only_100_filter(),
        4,
        page_size=2,
    )

    assert location.visible is True
    assert location.visible_index == 2
    assert location.page_start == 2
    assert location.local_row == 0


def test_filtered_hidden_source_row_is_reported_without_page_location(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stored.crt.jsonl"
    _write_session(path)

    location = locate_stored_search_row(
        path,
        _only_100_filter(),
        1,
        page_size=2,
    )

    assert location.visible is False
    assert location.visible_index is None
    assert location.page_start is None
    assert location.local_row is None
