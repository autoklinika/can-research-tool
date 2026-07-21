from __future__ import annotations

import hashlib

import pytest

from app.domain import (
    AnalysisInput,
    AnalysisStatus,
    ArtifactSource,
    ClaimSource,
    EvidenceReference,
    FindingStatus,
    FrameRangeReference,
    FrameReference,
    VerificationStatus,
)
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_domain_store import ProjectDomainStore
from app.project_migrations import PROJECT_DOMAIN_SCHEMA_VERSION
from app.session_stream import SessionStreamWriter


def test_project_domain_migration_is_idempotent_and_session_safe(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Domain foundation")
    first = _create_session(project, "first", frame_count=2)
    before = _sha256(project.absolute_path(first.relative_path))

    first_store = ProjectDomainStore(project)
    second_store = ProjectDomainStore(project)

    assert first_store.schema_version == PROJECT_DOMAIN_SCHEMA_VERSION
    assert second_store.schema_version == PROJECT_DOMAIN_SCHEMA_VERSION
    with project._connect() as connection:
        rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert rows == [(1, "project domain foundation")]
    assert _sha256(project.absolute_path(first.relative_path)) == before


def test_project_domain_store_preserves_provenance_and_evidence(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="ETC3 research")
    first = _create_session(project, "seed-key-ok", frame_count=3)
    second = _create_session(project, "invalid-key", frame_count=2)
    source_hashes = {
        first.id: _sha256(project.absolute_path(first.relative_path)),
        second.id: _sha256(project.absolute_path(second.relative_path)),
    }

    store = ProjectDomainStore(project)
    profile = store.update_profile(
        manufacturer="DAF",
        family="ETC3",
        model="ECU 001",
        processor="MPC5566",
    )
    assert profile.project_id == project.manifest.id
    assert profile.family == "ETC3"

    claim = store.add_profile_claim(
        field_name="software_version",
        value="candidate-from-diagnostic-session",
        source=ClaimSource.DETERMINISTIC_ANALYSIS,
        verification_status=VerificationStatus.TO_VERIFY,
        confidence=0.8,
        evidence=(
            EvidenceReference.frame(
                FrameReference(
                    session_id=first.id,
                    source_row=1,
                    sequence=1,
                    timestamp_ns=1_000_000,
                )
            ),
        ),
    )
    assert claim.profile_id == profile.id
    assert claim.verification_status == VerificationStatus.TO_VERIFY

    comparison = store.create_comparison_set(
        name="SecurityAccess OK versus InvalidKey",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
        synchronization_mode="marker",
        parameters={"marker": "security_access"},
    )
    assert comparison.session_ids == (first.id, second.id)

    run = store.create_analysis_run(
        provider_id="crt.test.reference_analysis",
        provider_version="1.0.0",
        algorithm_version="1",
        inputs=(AnalysisInput(kind="comparison_set", source_id=comparison.id),),
        parameters={"mode": "contract-test"},
    )
    store.set_analysis_status(run.id, AnalysisStatus.RUNNING)
    store.set_analysis_status(run.id, AnalysisStatus.COMPLETED)

    artifact = store.create_artifact(
        analysis_run_id=run.id,
        artifact_type="reference_artifact",
        schema_version=1,
        provider_id=run.provider_id,
        provider_version=run.provider_version,
        algorithm_version=run.algorithm_version,
        sources=(
            ArtifactSource(
                session_id=first.id,
                source_kind="frame_range",
                source_reference=FrameRangeReference(
                    session_id=first.id,
                    start_source_row=0,
                    end_source_row=2,
                ).to_dict(),
            ),
        ),
        relative_path="artifacts/reference/result.json",
        sha256="a" * 64,
        metadata={"result": "ok"},
    )

    finding = store.create_finding(
        title="Possible SecurityAccess lockout",
        description="The negative session differs from the accepted sequence.",
        finding_type="security_access",
        status=FindingStatus.TO_VERIFY,
        confidence=0.75,
        evidence=(EvidenceReference.artifact(artifact.id),),
        algorithm_id=run.provider_id,
        algorithm_version=run.algorithm_version,
    )
    store.set_finding_status(
        finding.id,
        FindingStatus.CONFIRMED,
        operator_comment="Confirmed on a repeated bench test.",
    )

    with project._connect() as connection:
        profile_row = connection.execute(
            "SELECT manufacturer, family, processor FROM ecu_profiles"
        ).fetchone()
        claim_row = connection.execute(
            "SELECT source, verification_status, confidence FROM ecu_profile_claims"
        ).fetchone()
        comparison_rows = connection.execute(
            """
            SELECT session_id, role, sort_order
            FROM comparison_set_sessions
            ORDER BY sort_order
            """
        ).fetchall()
        run_row = connection.execute(
            "SELECT status FROM analysis_runs WHERE id = ?",
            (run.id,),
        ).fetchone()
        artifact_row = connection.execute(
            "SELECT artifact_type, schema_version, sha256 FROM artifacts WHERE id = ?",
            (artifact.id,),
        ).fetchone()
        finding_row = connection.execute(
            "SELECT status, confidence FROM findings WHERE id = ?",
            (finding.id,),
        ).fetchone()
        history = connection.execute(
            """
            SELECT old_status, new_status
            FROM finding_status_history
            WHERE finding_id = ?
            ORDER BY changed_at_utc, rowid
            """,
            (finding.id,),
        ).fetchall()

    assert profile_row == ("DAF", "ETC3", "MPC5566")
    assert claim_row == ("deterministic_analysis", "to_verify", 0.8)
    assert comparison_rows == [
        (first.id, "base", 0),
        (second.id, "compared", 1),
    ]
    assert run_row == ("completed",)
    assert artifact_row == ("reference_artifact", 1, "a" * 64)
    assert finding_row == ("confirmed", 0.75)
    assert history == [("", "to_verify"), ("to_verify", "confirmed")]

    assert _sha256(project.absolute_path(first.relative_path)) == source_hashes[first.id]
    assert _sha256(project.absolute_path(second.relative_path)) == source_hashes[second.id]


def test_project_domain_store_rejects_broken_references(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Reference validation")
    session = _create_session(project, "reference", frame_count=1)
    store = ProjectDomainStore(project)

    with pytest.raises(KeyError, match="unknown sessions"):
        store.create_comparison_set(
            name="Broken comparison",
            session_ids=(session.id, "missing-session"),
        )

    with pytest.raises(ValueError, match="outside the session"):
        store.add_profile_claim(
            field_name="software_version",
            value="invalid evidence",
            source=ClaimSource.DETERMINISTIC_ANALYSIS,
            evidence=(
                EvidenceReference.frame(
                    FrameReference(session_id=session.id, source_row=99)
                ),
            ),
        )

    run = store.create_analysis_run(
        provider_id="crt.test.reference_analysis",
        provider_version="1.0.0",
        algorithm_version="1",
        inputs=(AnalysisInput(kind="session", source_id=session.id),),
    )
    with pytest.raises(ValueError, match="invalid analysis transition"):
        store.set_analysis_status(run.id, AnalysisStatus.COMPLETED)

    with pytest.raises(ValueError, match="escapes project directory"):
        store.create_artifact(
            analysis_run_id=run.id,
            artifact_type="invalid",
            schema_version=1,
            provider_id=run.provider_id,
            provider_version=run.provider_version,
            algorithm_version=run.algorithm_version,
            sources=(
                ArtifactSource(
                    session_id=session.id,
                    source_kind="session",
                    source_reference={},
                ),
            ),
            relative_path="../outside.json",
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
    record = project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
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
