from __future__ import annotations

from pathlib import Path

from app.models import CaptureSession
from app.project import CrtProject
from app.session_management import remove_session, session_artifact_paths
from app.session_stream import SessionStreamWriter


def _project(tmp_path: Path) -> CrtProject:
    return CrtProject.create(tmp_path / "project", name="Session management test")


def _write_standard_artifacts(directory: Path, name: str) -> tuple[Path, ...]:
    primary = directory / f"{name}.crt.jsonl"
    artifacts = (
        primary,
        primary.with_name(f"{name}.frames.csv"),
        primary.with_name(f"{name}.messages.csv"),
        primary.with_name(f"{name}.markers.jsonl"),
        primary.with_suffix(primary.suffix + ".idx.json"),
    )
    for index, path in enumerate(artifacts):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"artifact-{index}", encoding="utf-8")
    return artifacts


def test_live_session_removal_deletes_index_links_and_all_artifacts(tmp_path: Path) -> None:
    project = _project(tmp_path)
    artifacts = _write_standard_artifacts(project.live_sessions_dir, "engine_test")
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


def test_imported_csv_removal_deletes_project_copies_but_preserves_external_original(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)

    external_original = tmp_path / "outside-project" / "original.csv"
    external_original.parent.mkdir(parents=True, exist_ok=True)
    external_original.write_text("original user file", encoding="utf-8")

    project_source_copy = project.imported_sessions_dir / "source" / "original.csv"
    project_source_copy.parent.mkdir(parents=True, exist_ok=True)
    project_source_copy.write_text("project copy", encoding="utf-8")

    target = project.imported_sessions_dir / "converted.crt.jsonl"
    writer = SessionStreamWriter(
        CaptureSession(
            name="Converted",
            source="imported-kvaser-csv",
            metadata={"original_file": project.relative_path(project_source_copy)},
        ),
        target,
    )
    writer.open()
    writer.close({"clean_close": True, "frame_count": 0})
    for sidecar in (
        target.with_name("converted.frames.csv"),
        target.with_name("converted.messages.csv"),
        target.with_name("converted.markers.jsonl"),
    ):
        sidecar.write_text("derived", encoding="utf-8")

    session = project.register_session(
        target,
        name="Converted",
        source="imported-kvaser-csv",
        status="ready",
    )
    artifacts = session_artifact_paths(project, session)

    assert project_source_copy in artifacts
    assert external_original.resolve() not in artifacts
    result = remove_session(project, session.id, delete_files=True)

    assert project.list_sessions() == []
    assert set(result.removed_files) == set(artifacts)
    assert all(not path.exists() for path in artifacts)
    assert external_original.read_text(encoding="utf-8") == "original user file"


def test_imported_crt_removal_deletes_project_copy_but_not_external_original(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)

    external_original = tmp_path / "external-session.crt.jsonl"
    external_original.write_text("external original", encoding="utf-8")
    project_artifacts = _write_standard_artifacts(project.imported_sessions_dir, "imported")
    session = project.register_session(
        project_artifacts[0],
        name="Imported",
        source="imported-crt-session",
        status="ready",
    )

    result = remove_session(project, session.id, delete_files=True)

    assert result.removed_files == project_artifacts
    assert all(not path.exists() for path in project_artifacts)
    assert external_original.read_text(encoding="utf-8") == "external original"


def test_external_path_in_import_metadata_is_never_deleted(tmp_path: Path) -> None:
    project = _project(tmp_path)
    external_original = tmp_path / "protected.csv"
    external_original.write_text("protected", encoding="utf-8")

    target = project.imported_sessions_dir / "protected.crt.jsonl"
    writer = SessionStreamWriter(
        CaptureSession(
            name="Protected",
            source="imported-kvaser-csv",
            metadata={"original_file": str(external_original.resolve())},
        ),
        target,
    )
    writer.open()
    writer.close({"clean_close": True, "frame_count": 0})
    session = project.register_session(
        target,
        name="Protected",
        source="imported-kvaser-csv",
        status="ready",
    )

    artifacts = session_artifact_paths(project, session)
    assert external_original.resolve() not in artifacts
    remove_session(project, session.id, delete_files=True)

    assert external_original.read_text(encoding="utf-8") == "protected"


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
    assert len(result.missing_files) == 4
    assert project.list_sessions() == []
