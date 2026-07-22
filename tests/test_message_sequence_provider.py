from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.comparison_analysis_service import ComparisonAnalysisService
from app.comparison_sets import ComparisonSetStore
from app.extensions import (
    MESSAGE_SEQUENCE_ALGORITHM_VERSION,
    MESSAGE_SEQUENCE_PROVIDER_ID,
    CancellationToken,
    ExtensionCancelled,
    ExtensionExecutionError,
)
from app.extensions.builtin import message_sequence as message_sequence_module
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_migrations import PROJECT_DOMAIN_SCHEMA_VERSION
from app.session_stream import SessionStreamWriter


def test_message_sequences_are_exact_deterministic_and_source_safe(
    tmp_path,
) -> None:
    project = CrtProject.create(
        tmp_path / "project",
        name="Message sequence comparison",
    )
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
        MESSAGE_SEQUENCE_PROVIDER_ID,
        comparison.id,
        parameters={"memory_sequence_threshold": 1},
        progress_callback=updates.append,
    )
    second = service.run(
        MESSAGE_SEQUENCE_PROVIDER_ID,
        comparison.id,
        parameters={"memory_sequence_threshold": 1},
    )

    first_artifact = first.artifacts[0]
    second_artifact = second.artifacts[0]
    first_payload = service.artifacts.read_json(first_artifact)
    second_payload = service.artifacts.read_json(second_artifact)

    assert first_payload == second_payload
    assert first_artifact.sha256 == second_artifact.sha256
    assert first_artifact.artifact_type == "message_sequence_differences"
    assert first_artifact.schema_version == 1
    assert first_payload["schema"] == "crt.message_sequence_differences"
    assert first_payload["generated_by"] == {
        "provider_id": MESSAGE_SEQUENCE_PROVIDER_ID,
        "provider_version": "1.0.0",
        "algorithm_version": MESSAGE_SEQUENCE_ALGORITHM_VERSION,
        "crt_api": "1",
    }
    assert first_payload["summary"]["session_count"] == 2
    assert first_payload["summary"]["baseline_session_id"] == before.id
    assert first_payload["summary"]["matrix_complete"] is True
    assert first_payload["summary"]["sequence_lengths"] == [2, 3]
    assert first_payload["summary"]["sequence_modes"] == [
        "raw",
        "collapsed",
    ]
    assert first_payload["storage"] == {
        "mode": "bounded_memory_sqlite_exact",
        "memory_sequence_threshold": 1,
        "sequence_tracking_complete": True,
        "untracked_sequence_count": 0,
        "temporary_store_scope": "analysis_run",
    }

    sessions = {item["id"]: item for item in first_payload["sessions"]}
    baseline = sessions[before.id]
    current = sessions[after.id]
    assert baseline["role"] == "base"
    assert baseline["observed_frame_count"] == 5
    assert baseline["raw_pair_occurrence_count"] == 4
    assert baseline["raw_triple_occurrence_count"] == 3
    assert baseline["collapsed_pair_occurrence_count"] == 3
    assert baseline["collapsed_triple_occurrence_count"] == 2
    assert baseline["raw_pair_unique_count"] == 4
    assert baseline["unique_cycle_sequence_count"] == 2
    assert baseline["buffer_flush_count"] > 1

    assert current["role"] == "compared"
    assert current["observed_frame_count"] == 5
    assert current["new_sequence_count"] == 10
    assert current["missing_sequence_count"] == 8
    assert current["unique_cycle_sequence_count"] == 2

    sequences = first_payload["sequences"]
    raw_self = next(
        item
        for item in sequences
        if item["mode"] == "raw"
        and item["sequence_length"] == 2
        and item["sequence_text"].endswith(
            "0:STD:100:data → 0:STD:100:data"
        )
    )
    assert raw_self["is_self_transition"] is True
    assert raw_self["baseline"]["occurrence_count"] == 1
    assert raw_self["sessions"][1]["present"] is False

    baseline_cycle = next(
        item
        for item in sequences
        if item["mode"] == "collapsed"
        and item["sequence_length"] == 3
        and item["sequence_text"].endswith(
            "0:STD:100:data → 0:STD:200:data → 0:STD:100:data"
        )
    )
    assert baseline_cycle["is_cycle"] is True
    assert baseline_cycle["baseline"]["mean_span_ns"] == 30.0

    changes = first_payload["ranked_changes"]
    assert any(
        item["mode"] == "raw"
        and item["sequence_length"] == 2
        and item["sequence_text"].endswith(
            "0:STD:200:data → 0:STD:300:data"
        )
        and item["reasons"] == ["new_sequence"]
        for item in changes
    )
    assert any(
        item["mode"] == "collapsed"
        and item["sequence_length"] == 3
        and item["sequence_text"].endswith(
            "0:STD:100:data → 0:STD:200:data → 0:STD:100:data"
        )
        and item["reasons"] == ["missing_sequence"]
        for item in changes
    )

    assert tuple(source.session_id for source in first_artifact.sources) == (
        before.id,
        after.id,
    )
    assert service.store.schema_version == PROJECT_DOMAIN_SCHEMA_VERSION
    assert ComparisonSetStore(project).is_locked(comparison.id)
    for session in (before, after):
        assert (
            _sha256(project.absolute_path(session.relative_path))
            == source_hashes[session.id]
        )

    assert updates[0].current == 0
    assert updates[-1].current == updates[-1].total == 11
    assert updates[-1].message == "saved message sequence differences"

    with project._connect() as connection:
        run_states = connection.execute(
            "SELECT status, error FROM analysis_runs ORDER BY created_at_utc"
        ).fetchall()
        finding_count = connection.execute(
            "SELECT COUNT(*) FROM findings"
        ).fetchone()[0]
    assert run_states == [("completed", ""), ("completed", "")]
    assert finding_count == 0


def test_message_sequences_cleanup_temporary_sqlite_after_cancellation(
    tmp_path,
    monkeypatch,
) -> None:
    project = CrtProject.create(
        tmp_path / "project",
        name="Cancelled message sequences",
    )
    first = _create_session(project, "first", _before_frames())
    second = _create_session(project, "second", _after_frames())
    comparison = ComparisonSetStore(project).create(
        name="Cancellation cleanup",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
    )
    cancellation = CancellationToken()
    created_directories: list[Path] = []
    original_temporary_directory = (
        message_sequence_module.tempfile.TemporaryDirectory
    )

    def tracked_temporary_directory(*args, **kwargs):
        directory = original_temporary_directory(*args, **kwargs)
        created_directories.append(Path(directory.name))
        return directory

    monkeypatch.setattr(
        message_sequence_module.tempfile,
        "TemporaryDirectory",
        tracked_temporary_directory,
    )

    def cancel_after_provider_started(update) -> None:
        if update.current == 0:
            cancellation.cancel()

    with pytest.raises(ExtensionCancelled):
        ComparisonAnalysisService(project).run(
            MESSAGE_SEQUENCE_PROVIDER_ID,
            comparison.id,
            cancellation=cancellation,
            progress_callback=cancel_after_provider_started,
        )

    assert created_directories
    assert all(not directory.exists() for directory in created_directories)
    with project._connect() as connection:
        state = connection.execute(
            """
            SELECT status, error
            FROM analysis_runs
            ORDER BY created_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
        artifact_count = connection.execute(
            "SELECT COUNT(*) FROM artifacts"
        ).fetchone()[0]
    assert state == ("cancelled", "cancelled by user")
    assert artifact_count == 0


def test_message_sequences_reject_invalid_parameters(tmp_path) -> None:
    project = CrtProject.create(
        tmp_path / "project",
        name="Invalid sequence parameter",
    )
    first = _create_session(project, "first", _before_frames())
    second = _create_session(project, "second", _after_frames())
    comparison = ComparisonSetStore(project).create(
        name="Invalid sequence threshold",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
    )

    with pytest.raises(
        ExtensionExecutionError,
        match="memory_sequence_threshold",
    ):
        ComparisonAnalysisService(project).run(
            MESSAGE_SEQUENCE_PROVIDER_ID,
            comparison.id,
            parameters={"memory_sequence_threshold": 0},
        )

    with project._connect() as connection:
        artifact_count = connection.execute(
            "SELECT COUNT(*) FROM artifacts"
        ).fetchone()[0]
    assert artifact_count == 0


def test_message_sequences_reject_synchronization_mode(tmp_path) -> None:
    project = CrtProject.create(
        tmp_path / "project",
        name="Unsupported sequence synchronization",
    )
    first = _create_session(project, "first", _before_frames())
    second = _create_session(project, "second", _after_frames())
    comparison = ComparisonSetStore(project).create(
        name="Marker synchronized",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
        synchronization_mode="marker",
    )

    with pytest.raises(
        ExtensionExecutionError,
        match="synchronization_mode none",
    ):
        ComparisonAnalysisService(project).run(
            MESSAGE_SEQUENCE_PROVIDER_ID,
            comparison.id,
        )


def _before_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100),
        _frame(1, 10, 0x100),
        _frame(2, 20, 0x200),
        _frame(3, 30, 0x100),
        _frame(4, 50, 0x300),
    ]


def _after_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100),
        _frame(1, 5, 0x200),
        _frame(2, 15, 0x300),
        _frame(3, 30, 0x100),
        _frame(4, 45, 0x300),
    ]


def _frame(
    sequence: int,
    timestamp_ns: int,
    arbitration_id: int,
) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=arbitration_id,
        data=bytes((sequence & 0xFF,)),
        channel=0,
        is_extended_id=False,
    )


def _create_session(
    project: CrtProject,
    name: str,
    frames: list[CanFrame],
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(
        name=name,
        source="test",
        bitrate=250_000,
        channel=0,
    )
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True})
    record = project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
    duration_s = (
        0.0
        if not frames
        else max(frame.timestamp_ns for frame in frames)
        / 1_000_000_000.0
    )
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
