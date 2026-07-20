from __future__ import annotations

from pathlib import Path

from app.filters import FilterMode, FilterPreset
from app.models import CanFrame, CaptureSession
from app.session_filters import load_filtered_session_page
from app.session_stream import SessionStreamWriter
from app.static_active_filters import StaticCombinedActiveFilterSet
from app.static_frame_adapter import static_frame_record


def _preset() -> FilterPreset:
    preset = FilterPreset.create("Static parity")
    preset.mode = FilterMode.INCLUDE
    preset.scope = ["live", "stored_session"]
    preset.root = {
        "type": "group",
        "operator": "and",
        "children": [
            {
                "type": "condition",
                "field": "can_id",
                "operator": "can_id_pattern",
                "values": ["0x18DA??00"],
            },
            {
                "type": "condition",
                "field": "payload",
                "operator": "payload_prefix",
                "values": ["62 F1 ??"],
            },
            {
                "type": "condition",
                "field": "channel",
                "operator": "eq",
                "values": ["1"],
            },
            {
                "type": "condition",
                "field": "rtr",
                "operator": "eq",
                "values": ["nie"],
            },
            {
                "type": "condition",
                "field": "error_frame",
                "operator": "eq",
                "values": ["nie"],
            },
        ],
    }
    return preset


def _frames() -> tuple[CanFrame, ...]:
    return (
        CanFrame(
            sequence=1,
            timestamp_ns=1_000,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("62 F1 90"),
            channel=1,
            is_extended_id=True,
        ),
        CanFrame(
            sequence=2,
            timestamp_ns=2_000,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("7F 22 31"),
            channel=1,
            is_extended_id=True,
        ),
        CanFrame(
            sequence=3,
            timestamp_ns=3_000,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("62 F1 91"),
            channel=2,
            is_extended_id=True,
        ),
        CanFrame(
            sequence=4,
            timestamp_ns=4_000,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("62 F1 92"),
            channel=1,
            is_extended_id=True,
            is_remote_frame=True,
        ),
        CanFrame(
            sequence=5,
            timestamp_ns=5_000,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("62 F1 93"),
            channel=1,
            is_extended_id=True,
            is_error_frame=True,
        ),
        CanFrame(
            sequence=6,
            timestamp_ns=6_000,
            arbitration_id=0x18DAAA00,
            data=bytes.fromhex("62 F1 AA 01"),
            channel=1,
            is_extended_id=True,
        ),
    )


def _write_session(path: Path, frames: tuple[CanFrame, ...]) -> None:
    session = CaptureSession(name="Static parity", source="test")
    with SessionStreamWriter(session, path, flush_every=1, index_stride=2) as writer:
        for frame in frames:
            writer.append(frame)


def test_stored_session_uses_the_same_static_decisions_as_live(tmp_path: Path) -> None:
    frames = _frames()
    path = tmp_path / "parity.crt.jsonl"
    _write_session(path, frames)
    original_bytes = path.read_bytes()

    preset = _preset()
    live_filters = StaticCombinedActiveFilterSet([preset], scope="live")
    stored_filters = StaticCombinedActiveFilterSet([preset], scope="stored_session")

    expected_sequences = tuple(
        frame.sequence
        for frame in frames
        if live_filters.decide(static_frame_record(frame)).visible
    )
    page = load_filtered_session_page(
        path,
        stored_filters,
        max_rows=20,
        start=0,
    )

    assert expected_sequences == (1, 6)
    assert tuple(frame.sequence for frame in page.frames) == expected_sequences
    assert page.total_frames == len(frames)
    assert page.visible_frames == len(expected_sequences)
    assert page.scanned_all_frames is True
    assert path.read_bytes() == original_bytes


def test_static_filtered_session_pagination_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "pagination.crt.jsonl"
    frames = tuple(
        CanFrame(
            sequence=index,
            timestamp_ns=index * 1_000,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("62 F1 90") if index % 2 == 0 else bytes.fromhex("7F 22 31"),
            channel=1,
            is_extended_id=True,
        )
        for index in range(20)
    )
    _write_session(path, frames)
    filters = StaticCombinedActiveFilterSet([_preset()], scope="stored_session")

    first = load_filtered_session_page(path, filters, max_rows=3, start=0)
    second = load_filtered_session_page(path, filters, max_rows=3, start=3)
    last = load_filtered_session_page(path, filters, max_rows=3, start=100)

    assert tuple(frame.sequence for frame in first.frames) == (0, 2, 4)
    assert tuple(frame.sequence for frame in second.frames) == (6, 8, 10)
    assert tuple(frame.sequence for frame in last.frames) == (18,)
    assert first.visible_frames == second.visible_frames == last.visible_frames == 10
    assert last.loaded_from_visible_index == 9
