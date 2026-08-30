from __future__ import annotations

import hashlib
import json

import pytest

from app.domain import AnalysisInput
from app.extensions import (
    AnalysisContext,
    ArtifactWriter,
    CancellationToken,
    ExtensionExecutionError,
    ExtensionRegistry,
    ExtensionRunner,
    FindingWriter,
    ProgressReporter,
    ProjectContext,
    SESSION_STATISTICS_ALGORITHM_VERSION,
    SESSION_STATISTICS_PROVIDER_ID,
    SessionStatisticsProvider,
    register_builtin_extensions,
)
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_domain_store import ProjectDomainStore
from app.session_stream import SessionStreamWriter


def test_builtin_registry_exposes_session_statistics_provider() -> None:
    registry = ExtensionRegistry()
    manifests = register_builtin_extensions(registry)
    manifests_by_id = {manifest.id: manifest for manifest in manifests}

    assert SESSION_STATISTICS_PROVIDER_ID in manifests_by_id
    manifest = manifests_by_id[SESSION_STATISTICS_PROVIDER_ID]
    assert manifest == SessionStatisticsProvider.manifest
    assert manifest.inputs == ("session",)
    assert manifest.outputs == ("session_statistics",)
    assert registry.get_analysis(SESSION_STATISTICS_PROVIDER_ID).manifest == manifest


def test_session_statistics_are_persistent_deterministic_and_evidence_linked(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Session statistics")
    session = _create_session(project, "mixed", _mixed_frames())
    session_path = project.absolute_path(session.relative_path)
    source_hash = _sha256(session_path)
    store = ProjectDomainStore(project)

    first_artifact, first_payload, first_updates = _execute_statistics(
        project,
        store,
        session.id,
        parameters={"scope": "all"},
    )
    second_artifact, second_payload, second_updates = _execute_statistics(
        project,
        store,
        session.id,
        parameters={"scope": "all"},
    )

    assert first_payload == second_payload
    assert first_artifact.sha256 == second_artifact.sha256
    assert first_artifact.sha256 == _sha256(project.absolute_path(first_artifact.relative_path))
    assert _sha256(session_path) == source_hash

    assert first_payload["schema"] == "crt.session_statistics"
    assert first_payload["schema_version"] == 1
    assert first_payload["generated_by"] == {
        "provider_id": SESSION_STATISTICS_PROVIDER_ID,
        "provider_version": "1.0.0",
        "algorithm_version": SESSION_STATISTICS_ALGORITHM_VERSION,
        "crt_api": "1",
    }
    assert first_payload["input"]["parameters"] == {"scope": "all"}
    assert first_payload["session"]["id"] == session.id
    assert first_payload["session"]["observed_frame_count"] == 6
    assert first_payload["session"]["sha256"] == session.sha256

    assert first_payload["totals"] == {
        "frame_count": 6,
        "payload_bytes": 8,
        "data_frame_count": 4,
        "remote_frame_count": 1,
        "error_frame_count": 1,
        "standard_frame_count": 4,
        "extended_frame_count": 2,
        "unique_arbitration_id_count": 2,
        "unique_message_key_count": 4,
        "first_sequence": 0,
        "last_sequence": 5,
        "first_timestamp_ns": 0,
        "last_timestamp_ns": 8_000_000,
        "min_timestamp_ns": 0,
        "max_timestamp_ns": 8_000_000,
        "timestamp_span_ns": 8_000_000,
        "timestamp_span_s": 0.008,
    }
    assert first_payload["channels"] == [
        {"channel": 0, "frame_count": 4},
        {"channel": 1, "frame_count": 2},
    ]
    assert first_payload["dlc_distribution"] == [
        {"dlc": 0, "frame_count": 2},
        {"dlc": 1, "frame_count": 1},
        {"dlc": 2, "frame_count": 2},
        {"dlc": 3, "frame_count": 1},
    ]

    standard_data = next(
        item
        for item in first_payload["messages"]
        if item["arbitration_id"] == 0x100 and item["frame_kind"] == "data"
    )
    assert standard_data["arbitration_id_hex"] == "100"
    assert standard_data["frame_count"] == 3
    assert standard_data["payload_bytes"] == 5
    assert standard_data["first_source_row"] == 0
    assert standard_data["last_source_row"] == 5
    assert standard_data["dlc_distribution"] == [
        {"dlc": 1, "frame_count": 1},
        {"dlc": 2, "frame_count": 2},
    ]
    assert standard_data["timing"] == {
        "interval_count": 2,
        "positive_interval_count": 2,
        "zero_interval_count": 0,
        "negative_interval_count": 0,
        "min_positive_interval_ns": 2_000_000,
        "max_positive_interval_ns": 6_000_000,
        "mean_positive_interval_ns": 4_000_000.0,
        "population_stddev_positive_interval_ns": 2_000_000.0,
        "mean_positive_frequency_hz": 250.0,
    }

    assert [update.current for update in first_updates] == [0, 6, 7]
    assert first_updates[-1].message == "saved session statistics"
    assert [update.current for update in second_updates] == [0, 6, 7]

    with project._connect() as connection:
        artifact_rows = connection.execute(
            """
            SELECT a.artifact_type, a.schema_version, s.source_kind, s.source_reference_json
            FROM artifacts a
            JOIN artifact_sources s ON s.artifact_id = a.id
            ORDER BY a.created_at_utc, s.sort_order
            """
        ).fetchall()
        run_states = connection.execute(
            "SELECT status, error FROM analysis_runs ORDER BY created_at_utc"
        ).fetchall()
        finding_count = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]

    assert len(artifact_rows) == 2
    assert all(row[0:3] == ("session_statistics", 1, "session") for row in artifact_rows)
    assert json.loads(artifact_rows[0][3]) == {
        "frame_count": 6,
        "sha256": session.sha256,
    }
    assert run_states == [("completed", ""), ("completed", "")]
    assert finding_count == 0


def test_empty_session_produces_valid_zero_statistics(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Empty statistics")
    session = _create_session(project, "empty", [])
    store = ProjectDomainStore(project)

    artifact, payload, updates = _execute_statistics(project, store, session.id)

    assert artifact.artifact_type == "session_statistics"
    assert payload["totals"]["frame_count"] == 0
    assert payload["totals"]["payload_bytes"] == 0
    assert payload["totals"]["first_timestamp_ns"] is None
    assert payload["totals"]["timestamp_span_ns"] is None
    assert payload["capture_timing"]["interval_count"] == 0
    assert payload["capture_timing"]["mean_positive_frequency_hz"] is None
    assert payload["channels"] == []
    assert payload["dlc_distribution"] == []
    assert payload["messages"] == []
    assert [update.current for update in updates] == [0, 1]


def test_timestamp_anomalies_are_reported_without_invalid_frequency(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Timestamp anomalies")
    frames = [
        _frame(0, 0, 0x321, b"\x00"),
        _frame(1, 1_000_000, 0x321, b"\x01"),
        _frame(2, 1_000_000, 0x321, b"\x02"),
        _frame(3, 500_000, 0x321, b"\x03"),
    ]
    session = _create_session(project, "anomalies", frames)
    store = ProjectDomainStore(project)

    _, payload, _ = _execute_statistics(project, store, session.id)
    timing = payload["messages"][0]["timing"]

    assert timing == {
        "interval_count": 3,
        "positive_interval_count": 1,
        "zero_interval_count": 1,
        "negative_interval_count": 1,
        "min_positive_interval_ns": 1_000_000,
        "max_positive_interval_ns": 1_000_000,
        "mean_positive_interval_ns": 1_000_000.0,
        "population_stddev_positive_interval_ns": 0.0,
        "mean_positive_frequency_hz": 1000.0,
    }
    assert payload["totals"]["last_timestamp_ns"] == 500_000
    assert payload["totals"]["max_timestamp_ns"] == 1_000_000
    assert payload["totals"]["timestamp_span_ns"] == 1_000_000


def test_provider_rejects_more_than_one_session_and_marks_run_failed(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Invalid statistics input")
    first = _create_session(project, "first", [_frame(0, 0, 0x100, b"\x01")])
    second = _create_session(project, "second", [_frame(0, 0, 0x200, b"\x02")])
    store = ProjectDomainStore(project)
    inputs = (
        AnalysisInput(kind="session", source_id=first.id),
        AnalysisInput(kind="session", source_id=second.id),
    )
    run = store.create_analysis_run(
        provider_id=SESSION_STATISTICS_PROVIDER_ID,
        provider_version=SessionStatisticsProvider.manifest.version,
        algorithm_version=SESSION_STATISTICS_ALGORITHM_VERSION,
        inputs=inputs,
    )
    cancellation = CancellationToken()
    context = _context(project, store, run, inputs, cancellation)
    registry = ExtensionRegistry()
    register_builtin_extensions(registry)

    with pytest.raises(ExtensionExecutionError, match="exactly one session input"):
        ExtensionRunner(registry=registry, store=store).execute_analysis(
            SESSION_STATISTICS_PROVIDER_ID,
            context,
        )

    with project._connect() as connection:
        state = connection.execute(
            "SELECT status, error FROM analysis_runs WHERE id = ?",
            (run.id,),
        ).fetchone()
        artifact_count = connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    assert state == ("failed", "session statistics requires exactly one session input")
    assert artifact_count == 0


def _execute_statistics(project, store, session_id, *, parameters=None):
    analysis_input = AnalysisInput(
        kind="session",
        source_id=session_id,
        parameters=dict(parameters or {}),
    )
    run = store.create_analysis_run(
        provider_id=SESSION_STATISTICS_PROVIDER_ID,
        provider_version=SessionStatisticsProvider.manifest.version,
        algorithm_version=SESSION_STATISTICS_ALGORITHM_VERSION,
        inputs=(analysis_input,),
        parameters=dict(parameters or {}),
    )
    cancellation = CancellationToken()
    updates = []
    context = _context(
        project,
        store,
        run,
        (analysis_input,),
        cancellation,
        updates=updates,
    )
    registry = ExtensionRegistry()
    register_builtin_extensions(registry)
    artifact = ExtensionRunner(registry=registry, store=store).execute_analysis(
        SESSION_STATISTICS_PROVIDER_ID,
        context,
    )
    payload = json.loads(project.absolute_path(artifact.relative_path).read_text(encoding="utf-8"))
    return artifact, payload, updates


def _context(project, store, run, inputs, cancellation, *, updates=None):
    return AnalysisContext(
        project=ProjectContext(project, cancellation),
        analysis_run_id=run.id,
        inputs=tuple(inputs),
        cancellation=cancellation,
        progress=ProgressReporter(None if updates is None else updates.append),
        artifact_writer=ArtifactWriter(
            project=project,
            store=store,
            analysis_run_id=run.id,
            provider_id=run.provider_id,
            provider_version=run.provider_version,
            algorithm_version=run.algorithm_version,
            cancellation=cancellation,
        ),
        finding_writer=FindingWriter(
            store=store,
            cancellation=cancellation,
            algorithm_id=run.provider_id,
            algorithm_version=run.algorithm_version,
        ),
    )


def _mixed_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100, b"\x01\x02", channel=0),
        _frame(1, 1_000_000, 0x18DAF900, b"\x03\x04\x05", channel=1, extended=True),
        _frame(2, 2_000_000, 0x100, b"\x06", channel=0),
        _frame(3, 4_000_000, 0x100, b"", channel=0, remote=True),
        _frame(4, 6_000_000, 0x18DAF900, b"", channel=1, extended=True, error=True),
        _frame(5, 8_000_000, 0x100, b"\x07\x08", channel=0),
    ]


def _frame(
    sequence: int,
    timestamp_ns: int,
    arbitration_id: int,
    data: bytes,
    *,
    channel: int = 0,
    extended: bool = False,
    remote: bool = False,
    error: bool = False,
) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=arbitration_id,
        data=data,
        channel=channel,
        is_extended_id=extended,
        is_remote_frame=remote,
        is_error_frame=error,
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
