from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.comparison_interframe_timing import (
    ComparisonInterFrameTimingService,
    INTERFRAME_TIMING_ARTIFACT_TYPE,
    StaleInterFrameTimingArtifact,
    analyze_comparison_interframe_timing,
    interframe_timing_result_from_payload,
    interframe_timing_result_to_payload,
)
from app.comparison_sets import ComparisonSetStore
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter


def test_interframe_timing_detects_jitter_gaps_and_session_deltas(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Timing")
    before = _create_session(project, "before", (0, 10, 20, 30, 70))
    after = _create_session(project, "after", (0, 12, 24, 36, 48))
    comparison = ComparisonSetStore(project).create(
        name="Before versus after",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )

    result = analyze_comparison_interframe_timing(
        project,
        comparison,
        "0:STD:100:data",
        gap_factor=3.0,
        percentile_sample_limit=128,
        maximum_gap_evidence_per_session=10,
    )

    baseline, current = result.sessions
    assert baseline.occurrence_count == 5
    assert baseline.positive_interval_count == 4
    assert baseline.median_interval_ns == pytest.approx(10_000_000)
    assert baseline.mean_interval_ns == pytest.approx(17_500_000)
    assert baseline.gap_count == 1
    assert len(baseline.gap_evidence) == 1
    assert baseline.gap_evidence[0].previous_source_row == 4
    assert baseline.gap_evidence[0].current_source_row == 6
    assert baseline.gap_evidence[0].interval_ns == 40_000_000
    assert current.median_interval_ns == pytest.approx(12_000_000)
    assert current.jitter_p95_p05_ns == pytest.approx(0)
    assert current.gap_count == 0

    comparison_row = result.comparisons[0]
    assert comparison_row.session_id == after.id
    assert comparison_row.median_interval_delta_percent == pytest.approx(20.0)
    assert comparison_row.frequency_delta_percent == pytest.approx(
        -16.666666,
        rel=1e-5,
    )
    assert comparison_row.gap_count_delta == -1


def test_interframe_timing_artifact_round_trips_without_rescanning(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(
        tmp_path / "project",
        name="Timing artifact",
    )
    before = _create_session(project, "before", (0, 10, 20, 30, 70))
    after = _create_session(project, "after", (0, 12, 24, 36, 48))
    comparison = ComparisonSetStore(project).create(
        name="Before versus after",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )

    service = ComparisonInterFrameTimingService(project)
    execution = service.run_and_save(
        comparison,
        "0:STD:100:data",
        gap_factor=3.0,
        percentile_sample_limit=128,
        maximum_gap_evidence_per_session=10,
    )
    stored = service.load_latest_compatible(
        comparison,
        message_key="0:STD:100:data",
    )

    assert execution.artifact.artifact_type == INTERFRAME_TIMING_ARTIFACT_TYPE
    assert stored is not None
    assert stored.artifact.id == execution.artifact.id
    assert stored.result == execution.result
    assert project.absolute_path(execution.artifact.relative_path).is_file()


def test_interframe_timing_payload_rejects_changed_session_fingerprint(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(
        tmp_path / "project",
        name="Timing stale",
    )
    before = _create_session(project, "before", (0, 10, 20, 30, 70))
    after = _create_session(project, "after", (0, 12, 24, 36, 48))
    comparison = ComparisonSetStore(project).create(
        name="Before versus after",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    result = analyze_comparison_interframe_timing(
        project,
        comparison,
        "0:STD:100:data",
        percentile_sample_limit=128,
    )
    records_by_id = {
        record.id: record
        for record in project.list_sessions()
    }
    records = tuple(
        records_by_id[session_id]
        for session_id in comparison.session_ids
    )
    payload = interframe_timing_result_to_payload(
        comparison,
        result,
        records=records,
    )
    changed = deepcopy(payload)
    changed["session_fingerprints"][0]["frame_count"] += 1

    with pytest.raises(
        StaleInterFrameTimingArtifact,
        match="frame count changed",
    ):
        interframe_timing_result_from_payload(
            changed,
            comparison_set=comparison,
            records=records,
        )


def _create_session(
    project: CrtProject,
    name: str,
    timestamps_ms: tuple[int, ...],
):
    frames: list[CanFrame] = []
    sequence = 0
    for index, timestamp_ms in enumerate(timestamps_ms):
        frames.append(
            CanFrame(
                sequence,
                timestamp_ms * 1_000_000,
                0x100,
                bytes((index,)),
                channel=0,
            )
        )
        sequence += 1
        if index in {1, 3}:
            frames.append(
                CanFrame(
                    sequence,
                    timestamp_ms * 1_000_000 + 1,
                    0x200,
                    b"\xAA",
                    channel=0,
                )
            )
            sequence += 1
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
    project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=(timestamps_ms[-1] - timestamps_ms[0]) / 1_000.0,
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(
            f"session was not registered: {path}"
        )
    return record
