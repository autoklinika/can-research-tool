from __future__ import annotations

import hashlib

import pytest

from app.comparison_analysis_service import ComparisonAnalysisService
from app.comparison_sets import ComparisonSetStore
from app.extensions import (
    PAYLOAD_DIFFERENCE_ALGORITHM_VERSION,
    PAYLOAD_DIFFERENCE_PROVIDER_ID,
    ExtensionExecutionError,
    ExtensionRegistry,
    PayloadDifferenceProvider,
    register_builtin_comparison_extensions,
)
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_migrations import PROJECT_DOMAIN_SCHEMA_VERSION
from app.session_stream import SessionStreamWriter


def test_comparison_registry_exposes_payload_difference_provider() -> None:
    registry = ExtensionRegistry()
    manifests = register_builtin_comparison_extensions(registry)

    manifest = PayloadDifferenceProvider.manifest
    assert manifest in manifests
    assert manifest.id == PAYLOAD_DIFFERENCE_PROVIDER_ID
    assert manifest.inputs == ("comparison_set",)
    assert manifest.outputs == ("payload_differences",)
    assert manifest.type.value == "comparison"
    assert registry.get_comparison(PAYLOAD_DIFFERENCE_PROVIDER_ID).manifest == manifest


def test_payload_difference_is_deterministic_and_source_safe(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Payload comparison")
    before = _create_session(project, "before", _before_frames())
    after = _create_session(project, "after", _after_frames())
    source_hashes = {
        session.id: _sha256(project.absolute_path(session.relative_path))
        for session in (before, after)
    }
    comparison = ComparisonSetStore(project).create(
        name="Payload before versus after",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    service = ComparisonAnalysisService(project)
    updates = []

    first = service.run(
        PAYLOAD_DIFFERENCE_PROVIDER_ID,
        comparison.id,
        progress_callback=updates.append,
    )
    second = service.run(PAYLOAD_DIFFERENCE_PROVIDER_ID, comparison.id)

    first_artifact = first.artifacts[0]
    second_artifact = second.artifacts[0]
    first_payload = service.artifacts.read_json(first_artifact)
    second_payload = service.artifacts.read_json(second_artifact)

    assert first_payload == second_payload
    assert first_artifact.sha256 == second_artifact.sha256
    assert first_artifact.artifact_type == "payload_differences"
    assert first_artifact.schema_version == 1
    assert first_payload["schema"] == "crt.payload_differences"
    assert first_payload["generated_by"] == {
        "provider_id": PAYLOAD_DIFFERENCE_PROVIDER_ID,
        "provider_version": "1.1.0",
        "algorithm_version": PAYLOAD_DIFFERENCE_ALGORITHM_VERSION,
        "crt_api": "1",
    }
    assert first_payload["comparison_set"]["id"] == comparison.id
    assert first_payload["comparison_set"]["effective_baseline_session_id"] == before.id
    assert first_payload["summary"]["session_count"] == 2
    assert first_payload["summary"]["union_payload_message_key_count"] == 5
    assert first_payload["summary"]["common_payload_message_key_count"] == 3

    sessions = {item["id"]: item for item in first_payload["sessions"]}
    assert sessions[before.id]["role"] == "base"
    assert sessions[before.id]["observed_data_frame_count"] == 8
    assert sessions[after.id]["role"] == "compared"
    assert sessions[after.id]["observed_data_frame_count"] == 8
    assert sessions[after.id]["new_payload_message_key_count"] == 1
    assert sessions[after.id]["missing_payload_message_key_count"] == 1

    changes = first_payload["ranked_changes"]
    assert _has_change(changes, 0x300, "new_message_key")
    assert _has_change(changes, 0x200, "missing_message_key")
    assert _has_byte_change(changes, 0x100, 0, "constant_byte_changed")
    assert _has_byte_change(changes, 0x100, 1, "byte_value_set_changed")
    assert _has_byte_change(changes, 0x400, 1, "byte_became_variable")
    assert _has_byte_change(changes, 0x500, 1, "byte_became_constant")
    assert _has_change(changes, 0x100, "new_payload_variant")
    assert _has_change(changes, 0x100, "missing_payload_variant")

    id_100 = next(
        item
        for item in first_payload["message_payload_profiles"]
        if item["arbitration_id"] == 0x100
    )
    baseline_byte_0 = id_100["baseline"]["byte_positions"][0]
    assert baseline_byte_0["classification"] == "constant"
    assert baseline_byte_0["dominant_value_hex"] == "10"
    current_row = next(
        item for item in id_100["sessions"] if item["session_id"] == after.id
    )
    current_byte_0 = current_row["payload_profile"]["byte_positions"][0]
    assert current_byte_0["classification"] == "constant"
    assert current_byte_0["dominant_value_hex"] == "11"
    variant_matrix = id_100["variant_matrix"]
    assert id_100["variant_matrix_complete"] is True
    assert any(
        item["payload_hex"] == "10 20" and item["role"] == "baseline_only"
        for item in variant_matrix
    )
    assert any(
        item["payload_hex"] == "11 22" and item["role"] == "comparison_only"
        for item in variant_matrix
    )
    baseline_variant = next(
        item
        for item in id_100["baseline"]["variants"]
        if item["payload_hex"] == "10 20"
    )
    assert baseline_variant["first_timestamp_ns"] == 0
    assert baseline_variant["last_timestamp_ns"] == 2

    assert tuple(source.session_id for source in first_artifact.sources) == (
        before.id,
        after.id,
    )
    assert first_artifact.sources[0].source_reference["role"] == "base"
    assert first_artifact.sources[1].source_reference["role"] == "comparison"
    assert ComparisonSetStore(project).is_locked(comparison.id)
    assert service.store.schema_version == PROJECT_DOMAIN_SCHEMA_VERSION

    for session in (before, after):
        assert _sha256(project.absolute_path(session.relative_path)) == source_hashes[
            session.id
        ]

    assert updates[0].current == 0
    assert updates[-1].current == updates[-1].total == 17
    assert updates[-1].message == "saved payload differences"

    with project._connect() as connection:
        run_states = connection.execute(
            "SELECT status, error FROM analysis_runs ORDER BY created_at_utc"
        ).fetchall()
        finding_count = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    assert run_states == [("completed", ""), ("completed", "")]
    assert finding_count == 0


def test_payload_variant_limit_is_explicit_and_does_not_invent_differences(
    tmp_path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Payload limit")
    before = _create_session(
        project,
        "before",
        [
            _frame(0, 0, 0x100, b"\x00"),
            _frame(1, 1, 0x100, b"\x01"),
            _frame(2, 2, 0x100, b"\x02"),
        ],
    )
    after = _create_session(
        project,
        "after",
        [
            _frame(0, 0, 0x100, b"\x00"),
            _frame(1, 1, 0x100, b"\x03"),
            _frame(2, 2, 0x100, b"\x04"),
        ],
    )
    comparison = ComparisonSetStore(project).create(
        name="Payload limit",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )

    result = ComparisonAnalysisService(project).run(
        PAYLOAD_DIFFERENCE_PROVIDER_ID,
        comparison.id,
        parameters={"max_variants_per_message": 1},
    )
    service = ComparisonAnalysisService(project)
    payload = service.artifacts.read_json(result.artifacts[0])
    changes = payload["ranked_changes"]

    assert _has_change(changes, 0x100, "variant_comparison_truncated")
    assert not _has_change(changes, 0x100, "new_payload_variant")
    assert not _has_change(changes, 0x100, "missing_payload_variant")
    message = payload["message_payload_profiles"][0]
    assert message["baseline"]["variant_tracking"]["complete"] is False
    after_row = next(
        item for item in message["sessions"] if item["session_id"] == after.id
    )
    assert after_row["payload_profile"]["variant_tracking"]["complete"] is False


def test_payload_difference_rejects_invalid_limit_without_touching_sources(
    tmp_path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Invalid payload limit")
    before = _create_session(
        project,
        "before",
        [_frame(0, 0, 0x100, b"\x00")],
    )
    after = _create_session(
        project,
        "after",
        [_frame(0, 0, 0x100, b"\x01")],
    )
    comparison = ComparisonSetStore(project).create(
        name="Invalid payload limit",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    hashes = {
        session.id: _sha256(project.absolute_path(session.relative_path))
        for session in (before, after)
    }

    with pytest.raises(
        ExtensionExecutionError,
        match="max_variants_per_message",
    ):
        ComparisonAnalysisService(project).run(
            PAYLOAD_DIFFERENCE_PROVIDER_ID,
            comparison.id,
            parameters={"max_variants_per_message": 0},
        )

    with project._connect() as connection:
        state = connection.execute(
            "SELECT status, error FROM analysis_runs ORDER BY created_at_utc DESC LIMIT 1"
        ).fetchone()
        artifact_count = connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    assert state[0] == "failed"
    assert "max_variants_per_message" in state[1]
    assert artifact_count == 0
    for session in (before, after):
        assert _sha256(project.absolute_path(session.relative_path)) == hashes[session.id]


def _before_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100, b"\x10\x20"),
        _frame(1, 1, 0x100, b"\x10\x21"),
        _frame(2, 2, 0x100, b"\x10\x20"),
        _frame(3, 3, 0x200, b"\xAA"),
        _frame(4, 4, 0x400, b"\x01\x02"),
        _frame(5, 5, 0x400, b"\x01\x02"),
        _frame(6, 6, 0x500, b"\x05\x06"),
        _frame(7, 7, 0x500, b"\x05\x07"),
    ]


def _after_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100, b"\x11\x20"),
        _frame(1, 1, 0x100, b"\x11\x22"),
        _frame(2, 2, 0x100, b"\x11\x22"),
        _frame(3, 3, 0x300, b"\xBB"),
        _frame(4, 4, 0x400, b"\x01\x02"),
        _frame(5, 5, 0x400, b"\x01\x03"),
        _frame(6, 6, 0x500, b"\x05\x08"),
        _frame(7, 7, 0x500, b"\x05\x08"),
    ]


def _frame(
    sequence: int,
    timestamp_ns: int,
    arbitration_id: int,
    data: bytes,
) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=arbitration_id,
        data=data,
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


def _has_change(
    changes: list[dict],
    arbitration_id: int,
    change_type: str,
) -> bool:
    return any(
        item["arbitration_id"] == arbitration_id
        and item["change_type"] == change_type
        for item in changes
    )


def _has_byte_change(
    changes: list[dict],
    arbitration_id: int,
    byte_index: int,
    change_type: str,
) -> bool:
    return any(
        item["arbitration_id"] == arbitration_id
        and item.get("byte_index") == byte_index
        and item["change_type"] == change_type
        for item in changes
    )


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
