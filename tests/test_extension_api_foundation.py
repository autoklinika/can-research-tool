from __future__ import annotations

import hashlib
import json

import pytest

from app.domain import (
    AnalysisInput,
    ArtifactSource,
    EvidenceReference,
    FindingStatus,
    FrameReference,
)
from app.extensions import (
    AnalysisContext,
    ArtifactWriter,
    CancellationToken,
    ExtensionCancelled,
    ExtensionExecutionError,
    ExtensionManifest,
    ExtensionPermission,
    ExtensionRegistrationError,
    ExtensionRegistry,
    ExtensionRunner,
    ExtensionType,
    FindingWriter,
    ProgressReporter,
    ProjectContext,
)
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_domain_store import ProjectDomainStore
from app.session_stream import SessionStreamWriter


class ReferenceAnalysisProvider:
    manifest = ExtensionManifest(
        id="crt.analysis.reference_contract",
        name="Reference contract analysis",
        version="1.0.0",
        crt_api="1",
        type=ExtensionType.ANALYSIS,
        inputs=("session",),
        outputs=("reference_artifact", "finding"),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.SESSION_READ,
            ExtensionPermission.ARTIFACT_WRITE,
            ExtensionPermission.FINDING_WRITE,
        ),
    )

    def run(self, context: AnalysisContext):
        source = context.project.session(context.inputs[0].source_id)
        first = source.frames.frame_at(0)
        context.progress.report(1, 2, "read source frame")
        artifact = context.artifact_writer.write_json(
            filename="reference.json",
            artifact_type="reference_artifact",
            schema_version=1,
            sources=(
                ArtifactSource(
                    session_id=source.id,
                    source_kind="frame",
                    source_reference={"source_row": 0},
                ),
            ),
            payload={
                "project_id": context.project.project_id,
                "session_id": source.id,
                "sequence": first.sequence,
                "can_id": first.arbitration_id,
                "data": first.data.hex(),
            },
        )
        finding = context.finding_writer.create(
            title="Reference provider result",
            description="The provider produced an evidence-linked artifact.",
            finding_type="contract_test",
            status=FindingStatus.TO_VERIFY,
            confidence=1.0,
            evidence=(EvidenceReference.artifact(artifact.id),),
        )
        context.progress.report(2, 2, "saved artifact and finding")
        return artifact, finding


class FailingAnalysisProvider:
    manifest = ExtensionManifest(
        id="crt.analysis.failing_contract",
        name="Failing contract analysis",
        version="1.0.0",
        crt_api="1",
        type=ExtensionType.ANALYSIS,
        inputs=("session",),
        outputs=(),
        permissions=(ExtensionPermission.SESSION_READ,),
    )

    def run(self, context: AnalysisContext):
        context.project.session(context.inputs[0].source_id).frames.frame_at(0)
        raise RuntimeError("controlled provider failure")


class ActiveProvider:
    manifest = ExtensionManifest(
        id="crt.active.test",
        name="Active test",
        version="1.0.0",
        crt_api="1",
        type=ExtensionType.ACTIVE_SCENARIO,
        inputs=("session",),
        outputs=(),
        requires_can_tx=True,
        permissions=(ExtensionPermission.CAN_TX,),
    )


class IncompatibleProvider:
    manifest = ExtensionManifest(
        id="crt.analysis.future_api",
        name="Future API provider",
        version="1.0.0",
        crt_api="2",
        type=ExtensionType.ANALYSIS,
        inputs=("session",),
        outputs=(),
        permissions=(ExtensionPermission.SESSION_READ,),
    )

    def run(self, context: AnalysisContext):
        return None


def test_extension_manifest_is_strict_and_round_trips() -> None:
    manifest = ExtensionManifest.from_mapping(
        {
            "id": "crt.analysis.uds_timing",
            "name": "UDS response timing",
            "version": "1.2.3",
            "crt_api": "1",
            "type": "analysis",
            "inputs": ["session", "comparison_set"],
            "outputs": ["uds_timing_artifact"],
            "live_supported": True,
            "requires_ai": False,
            "requires_can_tx": False,
            "permissions": ["project.read", "session.read", "artifact.write"],
        }
    )
    assert ExtensionManifest.from_json(manifest.to_json()) == manifest

    with pytest.raises(ValueError, match="invalid extension id"):
        ExtensionManifest(
            id="Invalid ID",
            name="Invalid",
            version="1.0.0",
            crt_api="1",
            type=ExtensionType.ANALYSIS,
            inputs=("session",),
            outputs=(),
        )
    with pytest.raises(ValueError, match="must be boolean"):
        ExtensionManifest.from_mapping(
            {
                "id": "crt.analysis.invalid_bool",
                "name": "Invalid bool",
                "version": "1.0.0",
                "crt_api": "1",
                "type": "analysis",
                "inputs": [],
                "outputs": [],
                "requires_can_tx": "false",
            }
        )
    with pytest.raises(ValueError, match="declared together"):
        ExtensionManifest(
            id="crt.analysis.invalid_permission",
            name="Invalid permission",
            version="1.0.0",
            crt_api="1",
            type=ExtensionType.ANALYSIS,
            inputs=("session",),
            outputs=(),
            permissions=(ExtensionPermission.CAN_TX,),
        )


def test_passive_registry_rejects_unsafe_or_incompatible_extensions() -> None:
    registry = ExtensionRegistry()
    manifest = registry.register(ReferenceAnalysisProvider())
    assert manifest.id == "crt.analysis.reference_contract"
    assert registry.get_analysis(manifest.id).manifest == manifest
    assert registry.manifests(
        extension_type=ExtensionType.ANALYSIS,
        input_kind="session",
    ) == (manifest,)

    with pytest.raises(ExtensionRegistrationError, match="duplicate extension id"):
        registry.register(ReferenceAnalysisProvider())
    with pytest.raises(ExtensionRegistrationError, match="rejects CAN TX"):
        registry.register(ActiveProvider())
    assert registry.try_register(IncompatibleProvider()) is False
    assert registry.load_errors[0].extension_id == "crt.analysis.future_api"
    assert "incompatible CRT extension API" in registry.load_errors[0].error


def test_analysis_provider_uses_read_only_context_and_controlled_writers(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Extension API")
    session = _create_session(project, "reference", frame_count=2)
    session_path = project.absolute_path(session.relative_path)
    source_hash = _sha256(session_path)
    store = ProjectDomainStore(project)
    analysis_input = AnalysisInput(kind="session", source_id=session.id)
    run = store.create_analysis_run(
        provider_id=ReferenceAnalysisProvider.manifest.id,
        provider_version=ReferenceAnalysisProvider.manifest.version,
        algorithm_version="1",
        inputs=(analysis_input,),
    )

    cancellation = CancellationToken()
    updates = []
    progress = ProgressReporter(updates.append)
    context = AnalysisContext(
        project=ProjectContext(project, cancellation),
        analysis_run_id=run.id,
        inputs=(analysis_input,),
        cancellation=cancellation,
        progress=progress,
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
    registry = ExtensionRegistry()
    registry.register(ReferenceAnalysisProvider())
    artifact, finding = ExtensionRunner(registry=registry, store=store).execute_analysis(
        ReferenceAnalysisProvider.manifest.id,
        context,
    )

    artifact_path = project.absolute_path(artifact.relative_path)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["session_id"] == session.id
    assert payload["sequence"] == 0
    assert artifact.sha256 == _sha256(artifact_path)
    assert finding.evidence == (EvidenceReference.artifact(artifact.id),)
    assert [update.current for update in updates] == [1, 2]
    assert progress.last.message == "saved artifact and finding"

    with project._connect() as connection:
        run_status = connection.execute(
            "SELECT status, error FROM analysis_runs WHERE id = ?",
            (run.id,),
        ).fetchone()
        artifact_count = connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        finding_count = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    assert run_status == ("completed", "")
    assert artifact_count == 1
    assert finding_count == 1
    assert _sha256(session_path) == source_hash


def test_provider_failure_is_isolated_and_does_not_modify_session(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Failure boundary")
    session = _create_session(project, "failure", frame_count=1)
    session_path = project.absolute_path(session.relative_path)
    source_hash = _sha256(session_path)
    store = ProjectDomainStore(project)
    analysis_input = AnalysisInput(kind="session", source_id=session.id)
    run = store.create_analysis_run(
        provider_id=FailingAnalysisProvider.manifest.id,
        provider_version=FailingAnalysisProvider.manifest.version,
        algorithm_version="1",
        inputs=(analysis_input,),
    )
    cancellation = CancellationToken()
    context = _context(
        project=project,
        store=store,
        run=run,
        analysis_input=analysis_input,
        cancellation=cancellation,
    )
    registry = ExtensionRegistry()
    registry.register(FailingAnalysisProvider())

    with pytest.raises(ExtensionExecutionError, match="controlled provider failure"):
        ExtensionRunner(registry=registry, store=store).execute_analysis(
            FailingAnalysisProvider.manifest.id,
            context,
        )

    with project._connect() as connection:
        status = connection.execute(
            "SELECT status, error FROM analysis_runs WHERE id = ?",
            (run.id,),
        ).fetchone()
    assert status == ("failed", "controlled provider failure")
    assert _sha256(session_path) == source_hash
    assert not (project.root / "artifacts" / run.id).exists()


def test_cancelled_or_invalid_artifact_write_leaves_no_partial_file(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Atomic artifacts")
    session = _create_session(project, "atomic", frame_count=1)
    store = ProjectDomainStore(project)
    analysis_input = AnalysisInput(kind="session", source_id=session.id)
    run = store.create_analysis_run(
        provider_id=ReferenceAnalysisProvider.manifest.id,
        provider_version=ReferenceAnalysisProvider.manifest.version,
        algorithm_version="1",
        inputs=(analysis_input,),
    )
    cancellation = CancellationToken()
    writer = ArtifactWriter(
        project=project,
        store=store,
        analysis_run_id=run.id,
        provider_id=run.provider_id,
        provider_version=run.provider_version,
        algorithm_version=run.algorithm_version,
        cancellation=cancellation,
    )

    cancellation.cancel()
    with pytest.raises(ExtensionCancelled):
        writer.write_json(
            filename="cancelled.json",
            artifact_type="reference_artifact",
            schema_version=1,
            sources=(
                ArtifactSource(
                    session_id=session.id,
                    source_kind="session",
                    source_reference={},
                ),
            ),
            payload={"cancelled": True},
        )
    assert not (project.root / "artifacts" / run.id).exists()

    cancellation = CancellationToken()
    writer = ArtifactWriter(
        project=project,
        store=store,
        analysis_run_id=run.id,
        provider_id=run.provider_id,
        provider_version=run.provider_version,
        algorithm_version=run.algorithm_version,
        cancellation=cancellation,
    )
    with pytest.raises(ValueError, match="outside the session"):
        writer.write_json(
            filename="invalid.json",
            artifact_type="reference_artifact",
            schema_version=1,
            sources=(
                ArtifactSource(
                    session_id=session.id,
                    source_kind="frame",
                    source_reference={"source_row": 99},
                ),
            ),
            payload={"invalid": True},
        )
    output_dir = project.root / "artifacts" / run.id
    assert output_dir.is_dir()
    assert list(output_dir.iterdir()) == []


def _context(*, project, store, run, analysis_input, cancellation):
    return AnalysisContext(
        project=ProjectContext(project, cancellation),
        analysis_run_id=run.id,
        inputs=(analysis_input,),
        cancellation=cancellation,
        progress=ProgressReporter(),
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


def _create_session(project: CrtProject, name: str, *, frame_count: int):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for sequence in range(frame_count):
        writer.append(
            CanFrame(
                sequence=sequence,
                timestamp_ns=sequence * 1_000_000,
                arbitration_id=0x18DAF900,
                data=bytes((sequence, 0xAA)),
                channel=0,
                is_extended_id=True,
            )
        )
    writer.close({"clean_close": True})
    record = project.register_session(path, name=name, source="test", status="ready")
    project.finalize_session(
        path,
        frame_count=frame_count,
        marker_count=0,
        duration_s=max(0.0, float(frame_count - 1) / 1000.0),
    )
    return project.session_by_path(path) or record


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
