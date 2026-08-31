from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.comparison_sets import ComparisonSetStore
from app.experiment_diff_service import ExperimentDiffService
from app.extensions.builtin.signal_discovery import SIGNAL_DISCOVERY_PROVIDER_ID
from app.marker_stream import MarkerStreamWriter, marker_path_for_session
from app.markers import CaptureMarker, MarkerPreset
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_analysis_service import SessionAnalysisService
from app.session_stream import SessionStreamWriter
from app.signal_candidate_service import SignalCandidateService


def test_candidate_engine_consolidates_latest_experiment_and_activity_artifacts(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Signal Candidates")
    target = MarkerPreset.create("EGR disconnected", "F3")
    control = MarkerPreset.create("Control", "F4")
    first = _create_session(
        project,
        "first",
        target,
        control,
        first_target_delay_ms=12,
        second_target_delay_ms=14,
    )
    second = _create_session(
        project,
        "second",
        target,
        control,
        first_target_delay_ms=16,
        second_target_delay_ms=18,
    )
    comparison = ComparisonSetStore(project).create(
        name="EGR A/B",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
    )
    hashes = {
        first.id: _sha256(project.absolute_path(first.relative_path)),
        second.id: _sha256(project.absolute_path(second.relative_path)),
    }

    experiment = ExperimentDiffService(project)
    options = experiment.marker_options(comparison.id)
    target_option = next(item for item in options if item.preset_id == target.id)
    control_option = next(item for item in options if item.preset_id == control.id)

    # Re-running exactly the same experiment must not overweight it in the
    # Candidate Engine. The service keeps the newest semantic configuration.
    for _ in range(2):
        experiment.run(
            comparison.id,
            target_selector=target_option.selector,
            control_selector=control_option.selector,
            pre_window_ms=30,
            post_window_ms=50,
        )

    session_analysis = SessionAnalysisService(project)
    for session in (first, second):
        session_analysis.run(
            SIGNAL_DISCOVERY_PROVIDER_ID,
            session.id,
            parameters={
                "channel": 0,
                "arbitration_id": 0x123,
                "is_extended_id": False,
                "frame_kind": "data",
            },
        )

    service = SignalCandidateService(project)
    selected = service.select_inputs(comparison.id)
    assert len(selected.experiment_artifacts) == 1
    assert len(selected.signal_discovery_artifacts) == 2
    assert selected.candidate_message_keys == ("0:STD:123:data",)

    result = service.run(comparison.id)
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.artifact_type == "signal_candidates"
    payload = service.read_artifact(artifact)

    assert payload["schema"] == "crt.signal_candidates"
    assert payload["ranking_contract"]["ai_used"] is False
    assert payload["summary"]["experiment_artifact_count"] == 1
    assert payload["summary"]["signal_discovery_artifact_count"] == 2
    assert payload["summary"]["candidate_count"] == 1
    assert payload["summary"]["strong_count"] == 1

    candidate = payload["candidates"][0]
    assert candidate["rank"] == 1
    assert candidate["candidate_key"] == "0:STD:123:data:B0.2"
    assert candidate["arbitration_id"] == 0x123
    assert candidate["byte_index"] == 0
    assert candidate["bit_index"] == 2
    assert candidate["candidate_score"] == pytest.approx(1.0)
    assert candidate["strength"] == "strong"
    assert candidate["support_count"] == 1
    assert candidate["strong_support_count"] == 1

    best = candidate["best_support"]
    assert best["target"]["event_count"] == 4
    assert best["target"]["eligible_event_count"] == 4
    assert best["target"]["changed_event_count"] == 4
    assert best["control"]["event_count"] == 2
    assert best["control"]["eligible_event_count"] == 2
    assert best["control"]["changed_event_count"] == 0
    assert best["direction"]["dominant"] == "0->1"
    assert best["direction"]["consistency_ratio"] == pytest.approx(1.0)
    assert best["timing"]["mean_delay_ns"] == pytest.approx(15_000_000.0)
    assert best["timing"]["median_delay_ns"] == pytest.approx(15_000_000.0)

    activity = candidate["activity_validation"]
    assert activity["status"] == "consistent"
    assert activity["artifact_count"] == 2
    assert activity["session_count"] == 2
    assert activity["coverage_ratio"] == pytest.approx(1.0)
    assert activity["variable_observation_count"] == 2
    assert activity["constant_observation_count"] == 0
    assert activity["transition_count"] >= 4

    evidence = candidate["evidence"]
    assert len(evidence) == 6
    target_evidence = [item for item in evidence if item["group"] == "target"]
    control_evidence = [item for item in evidence if item["group"] == "control"]
    assert len(target_evidence) == 4
    assert len(control_evidence) == 2
    assert all(item["experiment_artifact_id"] == selected.experiment_artifacts[0].id for item in evidence)
    assert all(item["before"]["source_row"] in {0, 4} for item in target_evidence)
    assert all(item["after"]["source_row"] in {1, 5} for item in target_evidence)
    assert all(item["before"]["source_row"] == 2 for item in control_evidence)
    assert all(item["after"]["source_row"] == 3 for item in control_evidence)

    for session_id, expected in hashes.items():
        record = next(item for item in project.list_sessions() if item.id == session_id)
        assert _sha256(project.absolute_path(record.relative_path)) == expected


def test_candidate_engine_requires_experiment_diff_artifact(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="No Experiment")
    first = _simple_session(project, "first")
    second = _simple_session(project, "second")
    comparison = ComparisonSetStore(project).create(
        name="empty",
        session_ids=(first.id, second.id),
    )

    with pytest.raises(ValueError, match="Brak artefaktu Experiment Diff"):
        SignalCandidateService(project).select_inputs(comparison.id)


def _create_session(
    project: CrtProject,
    name: str,
    target: MarkerPreset,
    control: MarkerPreset,
    *,
    first_target_delay_ms: int,
    second_target_delay_ms: int,
):
    session_path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    frames = (
        _frame(0, 90_000_000, b"\x00"),
        _frame(1, (100 + first_target_delay_ms) * 1_000_000, b"\x04"),
        _frame(2, 190_000_000, b"\x04"),
        _frame(3, 220_000_000, b"\x04"),
        _frame(4, 290_000_000, b"\x00"),
        _frame(5, (300 + second_target_delay_ms) * 1_000_000, b"\x04"),
    )
    writer = SessionStreamWriter(capture, session_path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True, "frame_count": len(frames)})
    record = project.register_session(session_path, name=name, source="test", status="ready")
    project.finalize_session(
        session_path,
        frame_count=len(frames),
        marker_count=3,
        duration_s=0.32,
    )

    markers = MarkerStreamWriter(
        marker_path_for_session(session_path),
        presets=(target, control),
    )
    markers.open()
    markers.append(CaptureMarker.from_preset(target, 100_000_000, source="test"))
    markers.append(CaptureMarker.from_preset(control, 200_000_000, source="test"))
    markers.append(CaptureMarker.from_preset(target, 300_000_000, source="test"))
    markers.close()
    return project.session_by_path(session_path) or record


def _simple_session(project: CrtProject, name: str):
    session_path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    writer = SessionStreamWriter(capture, session_path)
    writer.open()
    writer.append(_frame(0, 1_000_000, b"\x00"))
    writer.close({"clean_close": True, "frame_count": 1})
    record = project.register_session(session_path, name=name, source="test", status="ready")
    project.finalize_session(session_path, frame_count=1, marker_count=0, duration_s=0.001)
    return project.session_by_path(session_path) or record


def _frame(sequence: int, timestamp_ns: int, data: bytes) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=0x123,
        data=data,
        channel=0,
        is_extended_id=False,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
