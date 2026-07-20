from pathlib import Path

from app.markers import MarkerPreset
from app.project import CrtProject


def test_project_is_self_contained_and_reopenable(tmp_path: Path) -> None:
    root = tmp_path / "DAF_MX13"
    project = CrtProject.create(
        root,
        name="DAF MX13",
        description="Bench research",
        default_bitrate=250_000,
    )

    assert (root / "project.crt.json").is_file()
    assert (root / ".crt" / "project.sqlite").is_file()
    assert project.live_sessions_dir.is_dir()
    assert project.imported_sessions_dir.is_dir()
    assert (root / "attachments").is_dir()

    area = project.add_study_area("EGR")
    presets = [
        MarkerPreset.create("EGR odłączony", "F3", area="EGR"),
        MarkerPreset.create("EGR podłączony", "F4", area="EGR"),
    ]
    project.save_marker_presets(presets)

    reopened = CrtProject.open(root)
    assert reopened.manifest.name == "DAF MX13"
    assert [item.name for item in reopened.list_study_areas()] == [area.name]
    assert [item.shortcut for item in reopened.list_marker_presets()] == ["F3", "F4"]


def test_project_rejects_duplicate_active_marker_shortcuts(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Test")
    presets = [
        MarkerPreset.create("A", "F1"),
        MarkerPreset.create("B", "f1"),
    ]

    try:
        project.save_marker_presets(presets)
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate shortcuts must be rejected")
