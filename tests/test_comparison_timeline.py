from __future__ import annotations

from pathlib import Path

import pytest

from app.comparison_timeline import (
    ComparisonTimelineCancelled,
    SYNC_MESSAGE_KEY,
    SYNC_SESSION_START,
    build_comparison_timeline,
    parse_timeline_message_key,
)
from app.domain import ComparisonSet
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter


def test_session_start_timeline_preserves_source_rows_and_bounded_sampling(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Timeline")
    before = _create_session(
        project,
        "before",
        [
            _frame(0, 10_000_000, 0x100),
            _frame(1, 20_000_000, 0x200),
            _frame(2, 30_000_000, 0x300),
            _frame(3, 40_000_000, 0x400),
        ],
    )
    after = _create_session(
        project,
        "after",
        [
            _frame(0, 100_000_000, 0x100),
            _frame(1, 110_000_000, 0x200),
            _frame(2, 120_000_000, 0x300),
            _frame(3, 130_000_000, 0x400),
        ],
    )
    comparison = _comparison(before.id, after.id)

    result = build_comparison_timeline(
        project,
        comparison,
        synchronization_mode=SYNC_SESSION_START,
        max_events_per_session=3,
    )

    assert len(result.lanes) == 2
    assert result.warnings == ()
    for lane in result.lanes:
        assert lane.synchronized
        assert lane.anchor_source_row == 0
        assert lane.sample_stride == 2
        assert [event.source_row for event in lane.events] == [0, 2, 3]
        assert [event.relative_time_ns for event in lane.events] == [
            0,
            20_000_000,
            30_000_000,
        ]
        assert lane.events[0].message_key == "0:STD:100:data"


def test_message_key_timeline_aligns_each_session_to_exact_first_anchor(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Timeline")
    before = _create_session(
        project,
        "before",
        [
            _frame(0, 10_000_000, 0x100),
            _frame(1, 20_000_000, 0x200),
            _frame(2, 35_000_000, 0x300),
        ],
    )
    after = _create_session(
        project,
        "after",
        [
            _frame(0, 100_000_000, 0x100),
            _frame(1, 115_000_000, 0x300),
            _frame(2, 130_000_000, 0x200),
        ],
    )

    result = build_comparison_timeline(
        project,
        _comparison(before.id, after.id),
        synchronization_mode=SYNC_MESSAGE_KEY,
        anchor_message_key="0:std:200:DATA",
    )

    assert result.anchor_message_key == "0:STD:200:data"
    assert [lane.anchor_source_row for lane in result.lanes] == [1, 2]
    assert [lane.anchor_timestamp_ns for lane in result.lanes] == [
        20_000_000,
        130_000_000,
    ]
    assert result.lanes[0].events[1].relative_time_ns == 0
    assert result.lanes[1].events[2].relative_time_ns == 0
    assert result.minimum_relative_time_ns == -30_000_000
    assert result.maximum_relative_time_ns == 15_000_000


def test_message_key_anchor_is_retained_when_sampling_would_skip_it(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Timeline")
    before = _create_session(
        project,
        "before",
        [
            _frame(0, 0, 0x100),
            _frame(1, 10_000_000, 0x200),
            _frame(2, 20_000_000, 0x300),
            _frame(3, 30_000_000, 0x400),
        ],
    )
    after = _create_session(
        project,
        "after",
        [
            _frame(0, 100_000_000, 0x100),
            _frame(1, 110_000_000, 0x200),
            _frame(2, 120_000_000, 0x300),
            _frame(3, 130_000_000, 0x400),
        ],
    )

    result = build_comparison_timeline(
        project,
        _comparison(before.id, after.id),
        synchronization_mode=SYNC_MESSAGE_KEY,
        anchor_message_key="0:STD:200:data",
        max_events_per_session=3,
    )

    for lane in result.lanes:
        assert lane.sampled_frame_count == 3
        assert lane.anchor_source_row == 1
        assert [event.source_row for event in lane.events] == [0, 1, 3]
        anchor_event = next(event for event in lane.events if event.source_row == 1)
        assert anchor_event.relative_time_ns == 0


def test_missing_message_anchor_is_explicit_and_does_not_fake_alignment(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Timeline")
    before = _create_session(project, "before", [_frame(0, 0, 0x100)])
    after = _create_session(project, "after", [_frame(0, 0, 0x200)])

    result = build_comparison_timeline(
        project,
        _comparison(before.id, after.id),
        synchronization_mode=SYNC_MESSAGE_KEY,
        anchor_message_key="0:STD:100:data",
    )

    assert result.lanes[0].synchronized
    assert not result.lanes[1].synchronized
    assert result.lanes[1].events[0].relative_time_ns is None
    assert "nie zawiera kotwicy" in result.lanes[1].warning
    assert len(result.warnings) == 1


def test_timeline_build_is_cancellable_and_key_validation_is_strict(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Timeline")
    before = _create_session(project, "before", [_frame(0, 0, 0x100)])
    after = _create_session(project, "after", [_frame(0, 0, 0x100)])

    with pytest.raises(ComparisonTimelineCancelled):
        build_comparison_timeline(
            project,
            _comparison(before.id, after.id),
            should_cancel=lambda: True,
        )
    with pytest.raises(ValueError, match="at least three"):
        build_comparison_timeline(
            project,
            _comparison(before.id, after.id),
            max_events_per_session=2,
        )
    with pytest.raises(ValueError):
        parse_timeline_message_key("0:STD:800:data")
    with pytest.raises(ValueError):
        parse_timeline_message_key("0:STD:100:unknown")


def _comparison(before_id: str, after_id: str) -> ComparisonSet:
    return ComparisonSet(
        id="comparison",
        name="Before versus after",
        session_ids=(before_id, after_id),
        base_session_id=before_id,
    )


def _create_session(
    project: CrtProject,
    name: str,
    frames: list[CanFrame],
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    writer = SessionStreamWriter(
        CaptureSession(name=name, source="test", bitrate=250_000, channel=0),
        path,
    )
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True})
    project.register_session(path, name=name, source="test", status="ready")
    duration_s = 0.0 if len(frames) < 2 else (
        frames[-1].timestamp_ns - frames[0].timestamp_ns
    ) / 1e9
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=duration_s,
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(f"session was not registered: {path}")
    return record


def _frame(sequence: int, timestamp_ns: int, arbitration_id: int) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=arbitration_id,
        data=bytes([sequence & 0xFF]),
        channel=0,
    )
