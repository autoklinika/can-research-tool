from __future__ import annotations

import hashlib

import pytest

from app.artifact_catalog import ArtifactIntegrityError
from app.extensions.builtin import (
    SESSION_STATISTICS_PROVIDER_ID,
    SIGNAL_DISCOVERY_PROVIDER_ID,
)
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_analysis_service import SessionAnalysisService
from app.session_stream import SessionStreamWriter


def test_session_analysis_service_runs_builtin_provider_and_catalogs_artifact(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Analysis workflow")
    session = _create_session(project, "statistics", frame_count=4)
    session_path = project.absolute_path(session.relative_path)
    source_hash = _sha256(session_path)
    updates = []

    service = SessionAnalysisService(project)
    manifests = service.available_session_analyses()
    assert [manifest.id for manifest in manifests] == [
        SESSION_STATISTICS_PROVIDER_ID,
        SIGNAL_DISCOVERY_PROVIDER_ID,
    ]

    result = service.run(
        SESSION_STATISTICS_PROVIDER_ID,
        session.id,
        progress_callback=updates.append,
    )
    assert result.provider_id == SESSION_STATISTICS_PROVIDER_ID
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.artifact_type == "session_statistics"
    assert artifact.sources[0].session_id == session.id
    assert artifact.sources[0].source_kind == "session"
    assert updates[0].current == 0
    assert updates[-1].current == updates[-1].total

    catalogued = service.list_artifacts(session.id)
    assert [item.id for item in catalogued] == [artifact.id]
    payload = service.artifacts.read_json(catalogued[0])
    assert payload["session"]["id"] == session.id
    assert payload["totals"]["frame_count"] == 4
    assert payload["totals"]["unique_arbitration_id_count"] == 2
    assert _sha256(session_path) == source_hash

    with project._connect() as connection:
        status = connection.execute(
            "SELECT status, error FROM analysis_runs WHERE id = ?",
            (result.analysis_run_id,),
        ).fetchone()
    assert status == ("completed", "")


def test_artifact_catalog_detects_file_tampering(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Artifact integrity")
    session = _create_session(project, "tamper", frame_count=1)
    service = SessionAnalysisService(project)
    artifact = service.run(SESSION_STATISTICS_PROVIDER_ID, session.id).artifacts[0]
    artifact_path = service.artifacts.absolute_path(artifact)
    artifact_path.write_text('{"tampered":true}', encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError, match="SHA-256 mismatch"):
        service.artifacts.read_json(artifact)


def test_session_analysis_service_rejects_unknown_session(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Unknown input")
    service = SessionAnalysisService(project)

    with pytest.raises(KeyError, match="unknown session"):
        service.run(SESSION_STATISTICS_PROVIDER_ID, "missing-session")


def _create_session(project: CrtProject, name: str, *, frame_count: int):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for sequence in range(frame_count):
        writer.append(
            CanFrame(
                sequence=sequence,
                timestamp_ns=sequence * 2_000_000,
                arbitration_id=0x100 + (sequence % 2),
                data=bytes((sequence, 0xAA)),
                channel=0,
                is_extended_id=False,
            )
        )
    writer.close({"clean_close": True})
    record = project.register_session(path, name=name, source="test", status="ready")
    project.finalize_session(
        path,
        frame_count=frame_count,
        marker_count=0,
        duration_s=max(0.0, float(frame_count - 1) * 0.002),
    )
    return project.session_by_path(path) or record


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
