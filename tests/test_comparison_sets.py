from __future__ import annotations

import hashlib

import pytest

from app.comparison_sets import ComparisonSetStore
from app.domain import AnalysisInput
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_domain_store import ProjectDomainStore
from app.project_migrations import PROJECT_DOMAIN_SCHEMA_VERSION
from app.session_stream import SessionStreamWriter


def test_comparison_set_crud_preserves_sessions_and_schema(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Comparison sets")
    before = _create_session(project, "before-repair", frame_count=3)
    after = _create_session(project, "after-repair", frame_count=4)
    reference = _create_session(project, "reference", frame_count=2)
    hashes = {
        session.id: _sha256(project.absolute_path(session.relative_path))
        for session in (before, after, reference)
    }

    store = ComparisonSetStore(project)
    comparison_set = store.create(
        name="Before versus after repair",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )

    assert store.list() == [comparison_set]
    assert store.get(comparison_set.id) == comparison_set
    assert not store.is_locked(comparison_set.id)

    updated = store.update(
        comparison_set.id,
        name="Repair validation",
        session_ids=(after.id, before.id, reference.id),
        base_session_id=after.id,
        synchronization_mode="none",
    )

    assert updated.id == comparison_set.id
    assert updated.created_at_utc == comparison_set.created_at_utc
    assert updated.updated_at_utc >= comparison_set.updated_at_utc
    assert updated.session_ids == (after.id, before.id, reference.id)
    assert updated.base_session_id == after.id
    assert store.get(updated.id) == updated

    store.delete(updated.id)
    assert store.list() == []
    assert {session.id for session in project.list_sessions()} == {
        before.id,
        after.id,
        reference.id,
    }
    assert ProjectDomainStore(project).schema_version == PROJECT_DOMAIN_SCHEMA_VERSION
    for session in (before, after, reference):
        assert _sha256(project.absolute_path(session.relative_path)) == hashes[session.id]


def test_comparison_set_used_by_analysis_is_immutable(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Locked comparison")
    first = _create_session(project, "first", frame_count=1)
    second = _create_session(project, "second", frame_count=1)
    store = ComparisonSetStore(project)
    comparison_set = store.create(
        name="Locked source",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
    )

    domain_store = ProjectDomainStore(project)
    domain_store.create_analysis_run(
        provider_id="crt.test.comparison",
        provider_version="1.0.0",
        algorithm_version="1",
        inputs=(
            AnalysisInput(kind="comparison_set", source_id=comparison_set.id),
        ),
    )

    assert store.analysis_run_count(comparison_set.id) == 1
    assert store.is_locked(comparison_set.id)
    with pytest.raises(ValueError, match="referenced by analysis runs"):
        store.update(
            comparison_set.id,
            name="Changed",
            session_ids=(first.id, second.id),
            base_session_id=second.id,
        )
    with pytest.raises(ValueError, match="referenced by analysis runs"):
        store.delete(comparison_set.id)
    assert store.get(comparison_set.id) == comparison_set


def test_comparison_set_rejects_invalid_session_selection(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Invalid comparison")
    session = _create_session(project, "only", frame_count=1)
    store = ComparisonSetStore(project)

    with pytest.raises(ValueError, match="at least two sessions"):
        store.create(name="Too small", session_ids=(session.id,))

    with pytest.raises(KeyError, match="unknown sessions"):
        store.create(
            name="Missing source",
            session_ids=(session.id, "missing-session"),
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
