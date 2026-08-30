from __future__ import annotations

from pathlib import Path

import pytest

from app.comparison_timeline import (
    ComparisonTimelineCancelled,
    SYNC_EXPLICIT_EVENT,
    SYNC_MESSAGE_KEY,
    SYNC_OPERATOR_MARKER,
    SYNC_SESSION_START,
    build_comparison_timeline,
    parse_timeline_message_key,
)
from app.domain import ComparisonSet
from app.marker_stream import MarkerStreamWriter, marker_path_for_session
from app.markers import CaptureMarker, MarkerPreset
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter


def test_session_start_timeline_preserves_endpoints_and_bounded_sampling(
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

    result = build_comparison_timeline(
        project,
        _comparison(before.id, after.id),
        synchronization_mode=SYNC_SESSION_START,
        max_events_per_session=3,
    )

    assert len(result.lanes) == 2
    assert result.warnings == ()
    for lane in result.lanes:
        assert lane.synchronized
        assert lane.anchor_source_row == 0
        assert [event.source_row for event in lane.events] == [0, 2, 3]
        assert lane.events[0].relative_time_ns == 0
        assert lane.events[-1].relative_time_ns == 30_000_000
        assert lane.events[0].message_key == "0:STD:100:data"


def test_message_key_timeline_supports_nth_exact_occurrence(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Timeline")
    before = _create_session(
        project,
        "before",
        [
            _frame(0, 10_000_000, 0x200),
            _frame(1, 20_000_000, 0x100),
            _frame(2, 35_000_000, 0x200),
        ],
    )
    after = _create_session(
        project,
        "after",
        [
            _frame(0, 100_000_000, 0x200),
            _frame(1, 115_000_000, 0x300),
            _frame(2, 130_000_000, 0x200),
        ],
    )

    result = build_comparison_timeline(
        project,
        _comparison(before.id, after.id),
        synchronization_mode=SYNC_MESSAGE_KEY,
        anchor_message_key="0:std:200:DATA",
        anchor_occurrence=2,
    )

    assert result.anchor_message_key == "0:STD:200:data"
    assert result.anchor_occurrence == 2
    assert [lane.anchor_source_row for lane in result.lanes] == [2, 2]
    assert [lane.anchor_timestamp_ns for lane in result.lanes] == [
        35_000_000,
        130_000_000,
    ]
    assert result.lanes[0].events[2].relative_time_ns == 0
    assert result.lanes[1].events[2].relative_time_ns == 0


def test_operator_marker_uses_exact_marker_time_and_nearest_frame(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Marker timeline")
    before = _create_session(
        project,
        "before",
        [
            _frame(0, 0, 0x100),
            _frame(1, 100_000_000, 0x200),
            _frame(2, 200_000_000, 0x300),
        ],
        markers=[("EGR odłączony", 120_000_000)],
    )
    after = _create_session(
        project,
        "after",
        [
            _frame(0, 0, 0x100),
            _frame(1, 30_000_000, 0x200),
            _frame(2, 60_000_000, 0x300),
        ],
        markers=[("EGR odłączony", 20_000_000)],
    )

    result = build_comparison_timeline(
        project,
        _comparison(before.id, after.id),
        synchronization_mode=SYNC_OPERATOR_MARKER,
        anchor_marker_name="EGR odłączony",
    )

    assert result.anchor_marker_name == "EGR odłączony"
    assert result.warnings == ()
    assert [lane.anchor_timestamp_ns for lane in result.lanes] == [
        120_000_000,
        20_000_000,
    ]
    assert [lane.anchor_source_row for lane in result.lanes] == [1, 1]
    assert result.lanes[0].events[1].relative_time_ns == -20_000_000
    assert result.lanes[1].events[1].relative_time_ns == 10_000_000
    assert (
        result.lanes[0].anchor_reference["marker_name"]
        == "EGR odłączony"
    )


def test_explicit_event_rows_align_exact_source_rows(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Explicit timeline")
    before = _create_session(
        project,
        "before",
        [_frame(0, 0, 0x100), _frame(1, 10_000_000, 0x200)],
    )
    after = _create_session(
        project,
        "after",
        [_frame(0, 50_000_000, 0x100), _frame(1, 80_000_000, 0x200)],
    )

    result = build_comparison_timeline(
        project,
        _comparison(before.id, after.id),
        synchronization_mode=SYNC_EXPLICIT_EVENT,
        explicit_anchor_rows={before.id: 1, after.id: 0},
    )

    assert result.explicit_anchor_rows == tuple(
        sorted(((before.id, 1), (after.id, 0)))
    )
    assert [lane.anchor_source_row for lane in result.lanes] == [1, 0]
    assert result.lanes[0].events[1].relative_time_ns == 0
    assert result.lanes[1].events[0].relative_time_ns == 0


def test_missing_anchor_is_explicit_and_does_not_fake_alignment(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Timeline")
    before = _create_session(
        project,
        "before",
        [_frame(0, 0, 0x100)],
        markers=[("Start", 0)],
    )
    after = _create_session(project, "after", [_frame(0, 0, 0x200)])

    result = build_comparison_timeline(
        project,
        _comparison(before.id, after.id),
        synchronization_mode=SYNC_OPERATOR_MARKER,
        anchor_marker_name="Start",
    )

    assert result.lanes[0].synchronized
    assert not result.lanes[1].synchronized
    assert result.lanes[1].events[0].relative_time_ns is None
    assert "nie zawiera" in result.lanes[1].warning
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
    with pytest.raises(ValueError):
        parse_timeline_message_key("0:STD:800:data")
    with pytest.raises(ValueError):
        parse_timeline_message_key("0:STD:100:unknown")
    with pytest.raises(ValueError):
        build_comparison_timeline(
            project,
            _comparison(before.id, after.id),
            synchronization_mode=SYNC_EXPLICIT_EVENT,
            explicit_anchor_rows={},
        )


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
    *,
    markers: list[tuple[str, int]] | None = None,
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    writer = SessionStreamWriter(
        CaptureSession(
            name=name,
            source="test",
            bitrate=250_000,
            channel=0,
        ),
        path,
    )
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True})

    marker_values = markers or []
    if marker_values:
        presets = tuple(
            MarkerPreset.create(marker_name, f"F{index + 1}")
            for index, (marker_name, _timestamp) in enumerate(marker_values)
        )
        with MarkerStreamWriter(
            marker_path_for_session(path),
            presets=presets,
        ) as marker_writer:
            for preset, (_marker_name, timestamp_ns) in zip(
                presets,
                marker_values,
                strict=True,
            ):
                marker_writer.append(
                    CaptureMarker.from_preset(
                        preset,
                        timestamp_ns,
                        source="test",
                    )
                )

    project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
    duration_s = (
        0.0
        if len(frames) < 2
        else (frames[-1].timestamp_ns - frames[0].timestamp_ns) / 1e9
    )
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=len(marker_values),
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
