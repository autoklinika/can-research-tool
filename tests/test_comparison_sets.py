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

    history_preserved = store.delete(updated.id)
    assert history_preserved is False
    assert store.list() == []
    assert store.list(include_deleted=True) == []
    assert {session.id for session in project.list_sessions()} == {
        before.id,
        after.id,
        reference.id,
    }
    assert ProjectDomainStore(project).schema_version == PROJECT_DOMAIN_SCHEMA_VERSION
    for session in (before, after, reference):
        assert _sha256(project.absolute_path(session.relative_path)) == hashes[session.id]


def test_analysed_comparison_set_edit_creates_new_active_version(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Versioned comparison")
    first = _create_session(project, "first", frame_count=1)
    second = _create_session(project, "second", frame_count=1)
    third = _create_session(project, "third", frame_count=1)
    store = ComparisonSetStore(project)
    original = store.create(
        name="Original source",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
    )

    domain_store = ProjectDomainStore(project)
    run = domain_store.create_analysis_run(
        provider_id="crt.test.comparison",
        provider_version="1.0.0",
        algorithm_version="1",
        inputs=(AnalysisInput(kind="comparison_set", source_id=original.id),),
    )

    assert store.analysis_run_count(original.id) == 1
    assert store.is_locked(original.id)
    with pytest.raises(ValueError, match="referenced by analysis runs"):
        store.update(
            original.id,
            name="Changed in place",
            session_ids=(first.id, second.id),
            base_session_id=second.id,
        )

    replacement = store.fork(
        original.id,
        name="Revised source",
        session_ids=(second.id, first.id, third.id),
        base_session_id=second.id,
    )

    assert replacement.id != original.id
    assert replacement.name == "Revised source"
    assert replacement.session_ids == (second.id, first.id, third.id)
    assert replacement.base_session_id == second.id
    assert store.list() == [replacement]
    assert not store.is_locked(replacement.id)

    historical = store.get(original.id)
    assert ComparisonSetStore.is_deleted(historical)
    assert historical.name == original.name
    assert historical.session_ids == original.session_ids
    assert historical.base_session_id == original.base_session_id
    assert store.analysis_run_count(original.id) == 1

    with project._connect() as connection:
        input_id = connection.execute(
            """
            SELECT input_id
            FROM analysis_inputs
            WHERE analysis_run_id = ? AND input_kind = 'comparison_set'
            """,
            (run.id,),
        ).fetchone()[0]
    assert input_id == original.id

    all_sets = store.list(include_deleted=True)
    assert {item.id for item in all_sets} == {original.id, replacement.id}


def test_delete_analysed_comparison_hides_set_and_preserves_history(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Delete comparison")
    first = _create_session(project, "first", frame_count=1)
    second = _create_session(project, "second", frame_count=1)
    store = ComparisonSetStore(project)
    comparison_set = store.create(
        name="Analysed source",
        session_ids=(first.id, second.id),
        base_session_id=first.id,
    )
    domain_store = ProjectDomainStore(project)
    run = domain_store.create_analysis_run(
        provider_id="crt.test.comparison",
        provider_version="1.0.0",
        algorithm_version="1",
        inputs=(
            AnalysisInput(kind="comparison_set", source_id=comparison_set.id),
        ),
    )

    history_preserved = store.delete(comparison_set.id)

    assert history_preserved is True
    assert store.list() == []
    historical = store.get(comparison_set.id)
    assert ComparisonSetStore.is_deleted(historical)
    assert store.analysis_run_count(comparison_set.id) == 1
    with project._connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM analysis_runs WHERE id = ?",
            (run.id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM analysis_inputs
            WHERE analysis_run_id = ? AND input_id = ?
            """,
            (run.id, comparison_set.id),
        ).fetchone()[0] == 1


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
