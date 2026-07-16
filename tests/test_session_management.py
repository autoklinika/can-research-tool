from __future__ import annotations

from pathlib import Path

import pytest

from app.project import CrtProject
from app.session_management import remove_session, session_artifact_paths


def _project(tmp_path: Path) -> CrtProject:
    return CrtProject.create(tmp_path / "project", name="Session management test")


def _write_live_artifacts(project: CrtProject, name: str) -> tuple[Path, ...]:
    primary = project.live_sessions_dir / f"{name}.crt.jsonl"
    artifacts = (
        primary,
        primary.with_name(f"{name}.frames.csv"),
        primary.with_name(f"{name}.messages.csv"),
        primary.with_name(f"{name}.markers.jsonl"),
    )
    for index, path in enumerate(artifacts):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"artifact-{index}", encoding="utf-8")
    return artifacts


def test_live_session_removal_deletes_index_links_and_all_artifacts(tmp_path: Path) -> None:
    project = _project(tmp_path)
    artifacts = _write_live_artifacts(project, "engine_test")
    session = project.register_session(
        artifacts[0],
        name="Engine test",
        source="kvaser-live-stream",
        status="ready",
    )
    area = project.add_study_area("EGR")
    project.link_session_to_area(session.id, area.id)

    assert session_artifact_paths(project, session) == artifacts
    result = remove_session(project, session.id, delete_files=True)

    assert result.session.id == session.id
    assert result.removed_files == artifacts
    assert result.missing_files == ()
    assert project.list_sessions() == []
    assert project.area_session_ids(area.id) == set()
    assert all(not path.exists() for path in artifacts)


def test_imported_session_removal_only_updates_project_index(tmp_path: Path) -> None:
    project = _project(tmp_path)
    target = project.imported_sessions_dir / "imported.crt.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("preserved import", encoding="utf-8")
    session = project.register_session(
        target,
        name="Imported",
        source="imported-crt-session",
        status="ready",
    )

    result = remove_session(project, session.id, delete_files=False)

    assert result.removed_files == ()
    assert result.missing_files == ()
    assert project.list_sessions() == []
    assert target.read_text(encoding="utf-8") == "preserved import"


def test_imported_session_files_cannot_be_deleted_by_service(tmp_path: Path) -> None:
    project = _project(tmp_path)
    target = project.imported_sessions_dir / "protected.crt.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("keep", encoding="utf-8")
    session = project.register_session(
        target,
        name="Protected",
        source="imported-kvaser-csv",
        status="ready",
    )

    with pytest.raises(ValueError, match="wyłącznie z listy"):
        remove_session(project, session.id, delete_files=True)

    assert project.session_by_path(target) is not None
    assert target.is_file()


def test_missing_live_sidecars_are_reported_but_do_not_block_removal(tmp_path: Path) -> None:
    project = _project(tmp_path)
    primary = project.live_sessions_dir / "partial.crt.jsonl"
    primary.parent.mkdir(parents=True, exist_ok=True)
    primary.write_text("session", encoding="utf-8")
    session = project.register_session(
        primary,
        name="Partial",
        source="kvaser-live-stream",
        status="ready",
    )

    result = remove_session(project, session.id, delete_files=True)

    assert result.removed_files == (primary,)
    assert len(result.missing_files) == 3
    assert project.list_sessions() == []
