from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.project import CrtProject
from app.project_catalog import ProjectCatalog, ProjectProfile, load_project_profile


def _set_last_opened(database_path: Path, project_id: str, value: datetime) -> None:
    import sqlite3

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE projects SET last_opened_at_utc = ? WHERE project_id = ?",
            (value.isoformat(), project_id),
        )
        connection.commit()


def test_register_search_and_remove_without_deleting_project(tmp_path: Path) -> None:
    project = CrtProject.create(
        tmp_path / "projects" / "man-md1",
        name="MAN TGX — MD1CE101",
        description="EGR bench investigation",
    )
    profile = ProjectProfile(
        vehicle_brand="MAN",
        vehicle_model="TGX",
        production_year=2021,
        vehicle_type="truck",
        vin="WMA06XZZ9MP123456",
        customer_name="Autoklinika",
        ecu_manufacturer="Bosch",
        ecu_type="MD1CE101",
        ecu_function="engine",
        part_number="0281039999",
        hardware_number="H21",
        software_number="1039S99999",
        ecu_status="after repair",
        tags=("Euro 6", "EGR"),
    )
    catalog = ProjectCatalog(tmp_path / "app-data" / "projects.sqlite")

    entry = catalog.register_project(project.root, profile=profile, opened=True)

    assert entry.project_id == project.manifest.id
    assert entry.available
    assert entry.profile.vehicle_brand == "MAN"
    assert load_project_profile(project.root) == profile.normalized()
    assert [item.project_id for item in catalog.list_projects(query="man md1 2021")] == [
        project.manifest.id
    ]
    assert [item.project_id for item in catalog.list_projects(query="egr euro")] == [
        project.manifest.id
    ]

    catalog.remove(project.manifest.id)

    assert catalog.list_projects() == []
    assert project.manifest_path.is_file()
    assert project.database_path.is_file()


def test_old_project_without_profile_is_compatible(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "legacy", name="Legacy CRT project")
    catalog = ProjectCatalog(tmp_path / "catalog.sqlite")

    entry = catalog.register_project(project.root)

    assert entry.profile == ProjectProfile()
    profile_path = project.root / "project-profile.json"
    assert profile_path.is_file()
    assert json.loads(profile_path.read_text(encoding="utf-8"))["vehicle_brand"] == ""


def test_time_filters_use_last_opened_activity(tmp_path: Path) -> None:
    catalog = ProjectCatalog(tmp_path / "catalog.sqlite")
    today_project = CrtProject.create(tmp_path / "today", name="Today")
    yesterday_project = CrtProject.create(tmp_path / "yesterday", name="Yesterday")
    old_project = CrtProject.create(tmp_path / "old", name="Old")
    for project in (today_project, yesterday_project, old_project):
        catalog.register_project(project.root)

    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    _set_last_opened(catalog.database_path, today_project.manifest.id, start_today + timedelta(hours=1))
    _set_last_opened(
        catalog.database_path,
        yesterday_project.manifest.id,
        start_today - timedelta(hours=1),
    )
    _set_last_opened(catalog.database_path, old_project.manifest.id, now - timedelta(days=40))

    assert [item.name for item in catalog.list_projects(time_filter="today")] == ["Today"]
    assert [item.name for item in catalog.list_projects(time_filter="yesterday")] == [
        "Yesterday"
    ]
    assert {item.name for item in catalog.list_projects(time_filter="7d")} == {
        "Today",
        "Yesterday",
    }
    assert {item.name for item in catalog.list_projects(time_filter="30d")} == {
        "Today",
        "Yesterday",
    }


def test_missing_project_is_marked_without_losing_catalog_entry(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "movable", name="Movable")
    catalog = ProjectCatalog(tmp_path / "catalog.sqlite")
    catalog.register_project(project.root)

    project.manifest_path.unlink()
    catalog.refresh_availability()

    entry = catalog.get(project.manifest.id)
    assert not entry.available
    assert catalog.list_projects(include_missing=False) == []
    assert catalog.list_projects(include_missing=True)[0].project_id == project.manifest.id


def test_registering_moved_project_updates_existing_catalog_location(tmp_path: Path) -> None:
    original = CrtProject.create(tmp_path / "original" / "project", name="Movable")
    catalog = ProjectCatalog(tmp_path / "catalog.sqlite")
    catalog.register_project(original.root)
    project_id = original.manifest.id

    moved_root = tmp_path / "moved" / "project"
    moved_root.parent.mkdir(parents=True)
    shutil.move(str(original.root), str(moved_root))
    catalog.refresh_availability()
    assert not catalog.get(project_id).available

    moved = CrtProject.open(moved_root)
    relocated = catalog.register_project(moved.root)

    assert relocated.project_id == project_id
    assert relocated.available
    assert relocated.root_path == str(moved_root.resolve())
    assert len(catalog.list_projects()) == 1


def test_profile_validation_and_tag_normalization() -> None:
    profile = ProjectProfile(
        production_year=2020,
        vehicle_brand=" MAN ",
        tags=("EGR", " EGR ", "Euro 6", ""),
    ).normalized()

    assert profile.vehicle_brand == "MAN"
    assert profile.tags == ("EGR", "Euro 6")
