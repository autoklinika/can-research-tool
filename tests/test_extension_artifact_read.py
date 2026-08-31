from __future__ import annotations

from pathlib import Path

import pytest

from app.artifact_catalog import ArtifactIntegrityError
from app.domain import AnalysisInput, ArtifactSource
from app.extensions import ArtifactWriter, CancellationToken, ProjectContext
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_domain_store import ProjectDomainStore
from app.session_stream import SessionStreamWriter


def test_artifact_read_requires_permission_and_returns_immutable_verified_snapshot(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="Artifact read")
    session = _session(project)
    store = ProjectDomainStore(project)
    analysis_input = AnalysisInput(kind="session", source_id=session.id)
    run = store.create_analysis_run(
        provider_id="crt.analysis.artifact_read_fixture",
        provider_version="1.0.0",
        algorithm_version="1",
        inputs=(analysis_input,),
    )
    token = CancellationToken()
    artifact = ArtifactWriter(
        project=project,
        store=store,
        analysis_run_id=run.id,
        provider_id=run.provider_id,
        provider_version=run.provider_version,
        algorithm_version=run.algorithm_version,
        cancellation=token,
    ).write_json(
        filename="fixture.json",
        artifact_type="fixture",
        schema_version=1,
        sources=(
            ArtifactSource(
                session_id=session.id,
                source_kind="session",
                source_reference={"sha256": session.sha256},
            ),
        ),
        payload={
            "schema": "crt.fixture",
            "nested": {"items": [1, 2, 3]},
        },
        metadata={"purpose": "artifact.read contract"},
    )

    without_permission = ProjectContext(project, token)
    with pytest.raises(PermissionError, match="artifact.read"):
        without_permission.artifact(artifact.id)

    context = ProjectContext(project, token, artifact_read_enabled=True)
    snapshot = context.artifact(artifact.id)
    assert snapshot.id == artifact.id
    assert snapshot.artifact_type == "fixture"
    assert snapshot.sha256 == artifact.sha256
    assert snapshot.payload["schema"] == "crt.fixture"
    assert snapshot.payload["nested"]["items"] == (1, 2, 3)

    with pytest.raises(TypeError):
        snapshot.payload["schema"] = "modified"
    with pytest.raises(TypeError):
        snapshot.payload["nested"]["other"] = True


def test_artifact_read_rejects_tampered_file(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Artifact integrity")
    session = _session(project)
    store = ProjectDomainStore(project)
    analysis_input = AnalysisInput(kind="session", source_id=session.id)
    run = store.create_analysis_run(
        provider_id="crt.analysis.artifact_integrity_fixture",
        provider_version="1.0.0",
        algorithm_version="1",
        inputs=(analysis_input,),
    )
    token = CancellationToken()
    artifact = ArtifactWriter(
        project=project,
        store=store,
        analysis_run_id=run.id,
        provider_id=run.provider_id,
        provider_version=run.provider_version,
        algorithm_version=run.algorithm_version,
        cancellation=token,
    ).write_json(
        filename="fixture.json",
        artifact_type="fixture",
        schema_version=1,
        sources=(
            ArtifactSource(
                session_id=session.id,
                source_kind="session",
                source_reference={},
            ),
        ),
        payload={"value": 1},
    )
    artifact_path = project.absolute_path(artifact.relative_path)
    artifact_path.write_text('{"value":2}\n', encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError, match="SHA-256 mismatch"):
        ProjectContext(project, token, artifact_read_enabled=True).artifact(artifact.id)


def _session(project: CrtProject):
    path = project.live_sessions_dir / "source.crt.jsonl"
    capture = CaptureSession(name="source", source="test", bitrate=250_000, channel=0)
    writer = SessionStreamWriter(capture, path)
    writer.open()
    writer.append(
        CanFrame(
            sequence=0,
            timestamp_ns=1_000_000,
            arbitration_id=0x123,
            data=b"\x04",
            channel=0,
            is_extended_id=False,
        )
    )
    writer.close({"clean_close": True, "frame_count": 1})
    record = project.register_session(path, name="source", source="test", status="ready")
    project.finalize_session(path, frame_count=1, marker_count=0, duration_s=0.001)
    return project.session_by_path(path) or record
