from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.comparison_sets import ComparisonSetStore
from app.comparison_timeline import SYNC_EXPLICIT_EVENT, build_comparison_timeline
from app.comparison_timeline_artifacts import (
    ComparisonTimelineArtifactService,
    StaleComparisonTimelineArtifact,
    TIMELINE_ALIGNMENT_ARTIFACT_TYPE,
    timeline_result_from_payload,
    timeline_result_to_payload,
)
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter


def test_saved_alignment_round_trips_without_rescanning_sessions(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Stored timeline")
    before = _create_session(project, "before", 0)
    after = _create_session(project, "after", 100_000_000)
    comparison = ComparisonSetStore(project).create(
        name="Before versus after",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    result = build_comparison_timeline(
        project,
        comparison,
        synchronization_mode=SYNC_EXPLICIT_EVENT,
        explicit_anchor_rows={before.id: 1, after.id: 2},
    )

    service = ComparisonTimelineArtifactService(project)
    artifact = service.save(comparison, result)
    stored = service.load_latest_compatible(comparison)

    assert artifact.artifact_type == TIMELINE_ALIGNMENT_ARTIFACT_TYPE
    assert stored is not None
    assert stored.artifact.id == artifact.id
    assert stored.result == result
    assert stored.configuration.explicit_rows == {
        before.id: 1,
        after.id: 2,
    }
    assert project.absolute_path(artifact.relative_path).is_file()


def test_alignment_payload_rejects_changed_session_fingerprint(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Stored timeline")
    before = _create_session(project, "before", 0)
    after = _create_session(project, "after", 100_000_000)
    comparison = ComparisonSetStore(project).create(
        name="Before versus after",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    result = build_comparison_timeline(project, comparison)
    records_by_id = {record.id: record for record in project.list_sessions()}
    records = tuple(
        records_by_id[session_id]
        for session_id in comparison.session_ids
    )
    payload = timeline_result_to_payload(
        comparison,
        result,
        records=records,
    )
    changed = deepcopy(payload)
    changed["session_fingerprints"][0]["frame_count"] += 1

    with pytest.raises(
        StaleComparisonTimelineArtifact,
        match="frame count changed",
    ):
        timeline_result_from_payload(
            changed,
            comparison_set=comparison,
            records=records,
        )


def test_latest_loader_skips_corrupted_newer_alignment(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Stored timeline")
    before = _create_session(project, "before", 0)
    after = _create_session(project, "after", 100_000_000)
    comparison = ComparisonSetStore(project).create(
        name="Before versus after",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    service = ComparisonTimelineArtifactService(project)
    result = build_comparison_timeline(project, comparison)
    first = service.save(comparison, result)
    second = service.save(comparison, result)
    project.absolute_path(second.relative_path).write_text(
        "{broken",
        encoding="utf-8",
    )

    stored = service.load_latest_compatible(comparison)

    assert stored is not None
    assert stored.artifact.id == first.id


def _create_session(project: CrtProject, name: str, offset_ns: int):
    frames = [
        CanFrame(0, offset_ns, 0x100, b"\x01", channel=0),
        CanFrame(1, offset_ns + 10_000_000, 0x200, b"\x02", channel=0),
        CanFrame(2, offset_ns + 20_000_000, 0x300, b"\x03", channel=0),
    ]
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
        duration_s=0.02,
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(f"session was not registered: {path}")
    return record
