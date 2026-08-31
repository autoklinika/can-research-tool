from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.comparison_sets import ComparisonSetStore
from app.experiment_diff_service import ExperimentDiffService
from app.marker_stream import MarkerStreamWriter, marker_path_for_session
from app.markers import CaptureMarker, MarkerPreset
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter


def test_repeated_target_change_is_ranked_above_unchanged_controls(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Experiment Diff")
    target = MarkerPreset.create("EGR disconnected", "F3")
    control = MarkerPreset.create("Control", "F4")

    first = _create_session(project, "first", target, control, target_delay_ms=12)
    second = _create_session(project, "second", target, control, target_delay_ms=16)
    source_hashes = {
        first.id: _sha256(project.absolute_path(first.relative_path)),
        second.id: _sha256(project.absolute_path(second.relative_path)),
    }
    comparison = ComparisonSetStore(project).create(
        name="EGR A/B",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
    )

    service = ExperimentDiffService(project)
    options = service.marker_options(comparison.id)
    target_option = next(item for item in options if item.preset_id == target.id)
    control_option = next(item for item in options if item.preset_id == control.id)
    assert target_option.event_count == 2
    assert target_option.session_count == 2
    assert control_option.event_count == 2

    result = service.run(
        comparison.id,
        target_selector=target_option.selector,
        control_selector=control_option.selector,
        pre_window_ms=30,
        post_window_ms=50,
    )
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.artifact_type == "experiment_marker_correlation"
    payload = service.analysis.artifacts.read_json(artifact)

    assert payload["schema"] == "crt.experiment_marker_correlation"
    assert payload["marker_selection"]["target_event_count"] == 2
    assert payload["marker_selection"]["control_event_count"] == 2
    assert payload["summary"]["candidate_count"] == 1

    candidate = payload["ranked_candidates"][0]
    assert candidate["arbitration_id"] == 0x123
    assert candidate["byte_index"] == 0
    assert candidate["bit_index"] == 2
    assert candidate["score"] == pytest.approx(1.0)
    assert candidate["target"] == {
        "event_count": 2,
        "eligible_event_count": 2,
        "changed_event_count": 2,
        "support_ratio": 1.0,
        "coverage_ratio": 1.0,
    }
    assert candidate["control"]["event_count"] == 2
    assert candidate["control"]["eligible_event_count"] == 2
    assert candidate["control"]["changed_event_count"] == 0
    assert candidate["control"]["change_ratio"] == 0.0
    assert candidate["control"]["specificity_ratio"] == 1.0
    assert candidate["direction"]["dominant"] == "0->1"
    assert candidate["direction"]["consistency_ratio"] == 1.0
    assert candidate["timing"]["mean_delay_ns"] == pytest.approx(14_000_000.0)
    assert candidate["timing"]["median_delay_ns"] == pytest.approx(14_000_000.0)

    evidence = candidate["evidence"]
    assert candidate["evidence_event_count"] == 4
    assert candidate["evidence_changed_event_count"] == 2
    assert not candidate["evidence_truncated"]
    assert len(evidence) == 4

    target_evidence = [item for item in evidence if item["group"] == "target"]
    assert len(target_evidence) == 2
    assert {item["session_id"] for item in target_evidence} == {first.id, second.id}
    assert all(item["changed"] for item in target_evidence)
    assert all(item["before"]["source_row"] == 0 for item in target_evidence)
    assert all(item["after"]["source_row"] == 1 for item in target_evidence)
    assert sorted(item["delay_ns"] for item in target_evidence) == [12_000_000, 16_000_000]

    control_evidence = [item for item in evidence if item["group"] == "control"]
    assert len(control_evidence) == 2
    assert {item["session_id"] for item in control_evidence} == {first.id, second.id}
    assert all(not item["changed"] for item in control_evidence)
    assert all(item["before_state"] == 1 and item["after_state"] == 1 for item in control_evidence)
    assert all(item["before"]["source_row"] == 2 for item in control_evidence)
    assert all(item["after"]["source_row"] == 3 for item in control_evidence)
    assert all(item["delay_ns"] is None for item in control_evidence)

    for session_id, expected_hash in source_hashes.items():
        record = next(item for item in project.list_sessions() if item.id == session_id)
        assert _sha256(project.absolute_path(record.relative_path)) == expected_hash


def test_marker_selector_prefers_immutable_preset_id_over_name(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Marker selector")
    preset = MarkerPreset.create("Original name", "F3")
    control = MarkerPreset.create("Control", "F4")
    session = _create_session(project, "first", preset, control, target_delay_ms=12)
    second = _create_session(project, "second", preset, control, target_delay_ms=14)
    comparison = ComparisonSetStore(project).create(
        name="selector",
        session_ids=(session.id, second.id),
    )

    # Captured snapshots may keep an old name after a preset is renamed. The
    # selector identity must stay tied to preset_id, not mutable display text.
    sidecar = marker_path_for_session(project.absolute_path(second.relative_path))
    records = _read_marker_records(sidecar)
    marker_record = next(record for record in records if record.get("record") == "marker")
    marker_record["name"] = "Renamed later"
    _write_marker_records(sidecar, records)

    options = ExperimentDiffService(project).marker_options(comparison.id)
    matching = [item for item in options if item.preset_id == preset.id]
    assert len(matching) == 1
    assert matching[0].event_count == 2
    assert matching[0].selector == f"preset:{preset.id}"


def _create_session(
    project: CrtProject,
    name: str,
    target: MarkerPreset,
    control: MarkerPreset,
    *,
    target_delay_ms: int,
):
    session_path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    target_after_ns = (100 + target_delay_ms) * 1_000_000
    frames = (
        _frame(0, 90_000_000, 0x123, b"\x00"),
        _frame(1, target_after_ns, 0x123, b"\x04"),
        _frame(2, 290_000_000, 0x123, b"\x04"),
        _frame(3, 320_000_000, 0x123, b"\x04"),
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
        marker_count=2,
        duration_s=0.32,
    )

    marker_writer = MarkerStreamWriter(
        marker_path_for_session(session_path),
        presets=(target, control),
    )
    marker_writer.open()
    marker_writer.append(
        CaptureMarker.from_preset(target, 100_000_000, source="test")
    )
    marker_writer.append(
        CaptureMarker.from_preset(control, 300_000_000, source="test")
    )
    marker_writer.close()
    return project.session_by_path(session_path) or record


def _frame(sequence: int, timestamp_ns: int, arbitration_id: int, data: bytes) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=arbitration_id,
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


def _read_marker_records(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_marker_records(path: Path, records) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
