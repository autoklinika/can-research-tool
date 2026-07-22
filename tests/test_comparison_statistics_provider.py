from __future__ import annotations

import hashlib

import pytest

from app.comparison_analysis_service import ComparisonAnalysisService
from app.comparison_sets import ComparisonSetStore
from app.extensions import (
    COMPARISON_STATISTICS_ALGORITHM_VERSION,
    COMPARISON_STATISTICS_PROVIDER_ID,
    ComparisonStatisticsProvider,
    ExtensionExecutionError,
    ExtensionRegistry,
    register_builtin_comparison_extensions,
)
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_migrations import PROJECT_DOMAIN_SCHEMA_VERSION
from app.session_stream import SessionStreamWriter


def test_comparison_registry_exposes_statistics_provider() -> None:
    registry = ExtensionRegistry()
    manifests = register_builtin_comparison_extensions(registry)

    assert manifests == (ComparisonStatisticsProvider.manifest,)
    assert manifests[0].id == COMPARISON_STATISTICS_PROVIDER_ID
    assert manifests[0].inputs == ("comparison_set",)
    assert manifests[0].outputs == ("comparison_statistics",)
    assert manifests[0].type.value == "comparison"
    assert registry.get_comparison(COMPARISON_STATISTICS_PROVIDER_ID).manifest == manifests[0]


def test_comparison_statistics_are_persistent_deterministic_and_source_safe(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Comparison statistics")
    before = _create_session(project, "before", _before_frames())
    after = _create_session(project, "after", _after_frames())
    source_hashes = {
        session.id: _sha256(project.absolute_path(session.relative_path))
        for session in (before, after)
    }
    comparison = ComparisonSetStore(project).create(
        name="Before versus after",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    service = ComparisonAnalysisService(project)
    updates = []

    first = service.run(
        COMPARISON_STATISTICS_PROVIDER_ID,
        comparison.id,
        progress_callback=updates.append,
    )
    second = service.run(COMPARISON_STATISTICS_PROVIDER_ID, comparison.id)

    first_artifact = first.artifacts[0]
    second_artifact = second.artifacts[0]
    first_payload = service.artifacts.read_json(first_artifact)
    second_payload = service.artifacts.read_json(second_artifact)

    assert first_payload == second_payload
    assert first_artifact.sha256 == second_artifact.sha256
    assert first_artifact.artifact_type == "comparison_statistics"
    assert first_artifact.schema_version == 1
    assert first_payload["schema"] == "crt.comparison_statistics"
    assert first_payload["generated_by"] == {
        "provider_id": COMPARISON_STATISTICS_PROVIDER_ID,
        "provider_version": "1.0.0",
        "algorithm_version": COMPARISON_STATISTICS_ALGORITHM_VERSION,
        "crt_api": "1",
    }
    assert first_payload["comparison_set"]["id"] == comparison.id
    assert first_payload["comparison_set"]["effective_baseline_session_id"] == before.id
    assert first_payload["summary"]["session_count"] == 2
    assert first_payload["summary"]["union_message_key_count"] == 3

    comparison_summary = first_payload["summary"]["comparisons"][0]
    assert comparison_summary["session_id"] == after.id
    assert comparison_summary["new_message_key_count"] == 1
    assert comparison_summary["missing_message_key_count"] == 1
    assert comparison_summary["common_message_key_count"] == 1
    assert comparison_summary["frequency_increase_count"] == 1
    assert comparison_summary["frequency_decrease_count"] == 0

    sessions = {item["id"]: item for item in first_payload["sessions"]}
    assert sessions[before.id]["role"] == "base"
    assert sessions[before.id]["observed_frame_count"] == 5
    assert sessions[after.id]["role"] == "compared"
    assert sessions[after.id]["observed_frame_count"] == 7

    changes = first_payload["notable_changes"]
    assert any(
        item["arbitration_id"] == 0x300 and item["reasons"] == ["new"]
        for item in changes
    )
    assert any(
        item["arbitration_id"] == 0x200 and item["reasons"] == ["missing"]
        for item in changes
    )
    id_100 = next(item for item in changes if item["arbitration_id"] == 0x100)
    assert "frequency_increase" in id_100["reasons"]
    assert id_100["baseline"]["mean_positive_frequency_hz"] == 10.0
    assert id_100["current"]["mean_positive_frequency_hz"] == 20.0
    assert id_100["frequency_delta_percent"] == 100.0

    assert tuple(source.session_id for source in first_artifact.sources) == (
        before.id,
        after.id,
    )
    assert first_artifact.sources[0].source_reference["role"] == "base"
    assert first_artifact.sources[1].source_reference["role"] == "compared"
    listed_artifact_ids = {item.id for item in service.list_artifacts(comparison.id)}
    assert listed_artifact_ids == {first_artifact.id, second_artifact.id}
    assert ComparisonSetStore(project).is_locked(comparison.id)
    assert service.store.schema_version == PROJECT_DOMAIN_SCHEMA_VERSION

    for session in (before, after):
        assert _sha256(project.absolute_path(session.relative_path)) == source_hashes[session.id]

    assert updates[0].current == 0
    assert updates[-1].current == updates[-1].total == 13
    assert updates[-1].message == "saved comparison statistics"

    with project._connect() as connection:
        run_states = connection.execute(
            "SELECT status, error FROM analysis_runs ORDER BY created_at_utc"
        ).fetchall()
        finding_count = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    assert run_states == [("completed", ""), ("completed", "")]
    assert finding_count == 0


def test_comparison_uses_first_session_as_effective_baseline(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Implicit baseline")
    first = _create_session(project, "first", [_frame(0, 0, 0x100)])
    second = _create_session(project, "second", [_frame(0, 0, 0x200)])
    comparison = ComparisonSetStore(project).create(
        name="Implicit baseline",
        session_ids=(first.id, second.id),
    )

    result = ComparisonAnalysisService(project).run(
        COMPARISON_STATISTICS_PROVIDER_ID,
        comparison.id,
    )
    payload = ComparisonAnalysisService(project).artifacts.read_json(result.artifacts[0])

    assert payload["comparison_set"]["base_session_id"] is None
    assert payload["comparison_set"]["effective_baseline_session_id"] == first.id
    assert payload["sessions"][0]["role"] == "base"


def test_comparison_rejects_invalid_threshold_without_touching_sources(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Invalid parameter")
    first = _create_session(project, "first", [_frame(0, 0, 0x100)])
    second = _create_session(project, "second", [_frame(0, 0, 0x100)])
    comparison = ComparisonSetStore(project).create(
        name="Invalid threshold",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
    )
    hashes = {
        session.id: _sha256(project.absolute_path(session.relative_path))
        for session in (first, second)
    }

    with pytest.raises(ExtensionExecutionError, match="frequency_change_threshold_percent"):
        ComparisonAnalysisService(project).run(
            COMPARISON_STATISTICS_PROVIDER_ID,
            comparison.id,
            parameters={"frequency_change_threshold_percent": -1},
        )

    with project._connect() as connection:
        state = connection.execute(
            "SELECT status, error FROM analysis_runs ORDER BY created_at_utc DESC LIMIT 1"
        ).fetchone()
        artifact_count = connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    assert state[0] == "failed"
    assert "frequency_change_threshold_percent" in state[1]
    assert artifact_count == 0
    for session in (first, second):
        assert _sha256(project.absolute_path(session.relative_path)) == hashes[session.id]


def test_comparison_rejects_unimplemented_synchronization_mode(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Unsupported synchronization")
    first = _create_session(project, "first", [_frame(0, 0, 0x100)])
    second = _create_session(project, "second", [_frame(0, 0, 0x100)])
    comparison = ComparisonSetStore(project).create(
        name="Marker synchronized",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
        synchronization_mode="marker",
    )

    with pytest.raises(ExtensionExecutionError, match="synchronization_mode none"):
        ComparisonAnalysisService(project).run(
            COMPARISON_STATISTICS_PROVIDER_ID,
            comparison.id,
        )

    with project._connect() as connection:
        state = connection.execute(
            "SELECT status, error FROM analysis_runs ORDER BY created_at_utc DESC LIMIT 1"
        ).fetchone()
        artifact_count = connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    assert state[0] == "failed"
    assert "synchronization_mode none" in state[1]
    assert artifact_count == 0


def _before_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100),
        _frame(1, 0, 0x200),
        _frame(2, 100_000_000, 0x100),
        _frame(3, 200_000_000, 0x100),
        _frame(4, 200_000_000, 0x200),
    ]


def _after_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100),
        _frame(1, 10_000_000, 0x300),
        _frame(2, 50_000_000, 0x100),
        _frame(3, 100_000_000, 0x100),
        _frame(4, 110_000_000, 0x300),
        _frame(5, 150_000_000, 0x100),
        _frame(6, 200_000_000, 0x100),
    ]


def _frame(sequence: int, timestamp_ns: int, arbitration_id: int) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=arbitration_id,
        data=bytes((sequence & 0xFF,)),
        channel=0,
        is_extended_id=False,
    )


def _create_session(project: CrtProject, name: str, frames: list[CanFrame]):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True})
    record = project.register_session(path, name=name, source="test", status="ready")
    duration_s = 0.0
    if frames:
        duration_s = max(frame.timestamp_ns for frame in frames) / 1_000_000_000.0
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=duration_s,
    )
    return project.session_by_path(path) or record


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
