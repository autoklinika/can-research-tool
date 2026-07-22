from __future__ import annotations

from pathlib import Path

from app.project import CrtProject


def test_project_manifest_edit_preserves_project_identity_and_data(tmp_path: Path) -> None:
    root = tmp_path / "project"
    project = CrtProject.create(
        root,
        name="DAF MX13",
        description="Initial description",
        default_bitrate=250_000,
        default_receive_mode="bench",
    )
    area = project.add_study_area("EGR")
    original_id = project.manifest.id
    original_created_at = project.manifest.created_at_utc
    database_path = project.database_path

    project.update_manifest(
        name="DAF MX13 — stanowisko 2",
        description="Updated description",
        default_bitrate=500_000,
        default_receive_mode="listen-only",
    )

    reopened = CrtProject.open(root)
    assert reopened.root == root.resolve()
    assert reopened.database_path == database_path
    assert reopened.database_path.is_file()
    assert reopened.manifest.id == original_id
    assert reopened.manifest.created_at_utc == original_created_at
    assert reopened.manifest.name == "DAF MX13 — stanowisko 2"
    assert reopened.manifest.description == "Updated description"
    assert reopened.manifest.default_bitrate == 500_000
    assert reopened.manifest.default_receive_mode == "listen-only"
    assert [item.id for item in reopened.list_study_areas()] == [area.id]
