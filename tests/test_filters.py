from __future__ import annotations

from pathlib import Path

from app.filters import (
    CanFrameRecord,
    FilterCompiler,
    FilterPreset,
    MatchState,
    ProjectFilterRepository,
)
from app.project import CrtProject


def test_filter_engine_matches_nested_can_conditions() -> None:
    preset = FilterPreset.create("EGR")
    preset.root = {
        "type": "group",
        "operator": "and",
        "children": [
            {
                "type": "condition",
                "field": "can_id",
                "operator": "eq",
                "values": ["0x18FEAE30"],
            },
            {
                "type": "group",
                "operator": "or",
                "children": [
                    {
                        "type": "condition",
                        "field": "dlc",
                        "operator": "eq",
                        "values": [8],
                    },
                    {
                        "type": "condition",
                        "field": "dlc",
                        "operator": "eq",
                        "values": [64],
                    },
                ],
            },
        ],
    }
    compiler = FilterCompiler()

    assert compiler.validate(preset) == []
    assert compiler.evaluate(
        preset,
        CanFrameRecord(can_id=0x18FEAE30, extended=True, dlc=8),
    ).state == MatchState.MATCH
    assert compiler.evaluate(
        preset,
        CanFrameRecord(can_id=0x18FEAE31, extended=True, dlc=8),
    ).state == MatchState.NO_MATCH


def test_invalid_not_group_returns_unavailable() -> None:
    preset = FilterPreset.create("Invalid")
    preset.root = {"type": "group", "operator": "not", "children": []}
    compiler = FilterCompiler()

    issues = compiler.validate(preset)
    assert issues
    result = compiler.evaluate(
        preset,
        CanFrameRecord(can_id=1, extended=False, dlc=1),
    )
    assert result.state == MatchState.UNAVAILABLE


def test_filter_presets_round_trip_in_project_database(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Filters")
    repository = ProjectFilterRepository(project.database_path)
    preset = FilterPreset.create("UDS")
    preset.shortcut = "F8"
    preset.root = {
        "type": "group",
        "operator": "and",
        "children": [
            {
                "type": "condition",
                "field": "can_id",
                "operator": "in",
                "values": ["0x18DA30F9", "0x18DAF930"],
            }
        ],
    }

    repository.save_presets([preset])
    loaded = repository.list_presets()

    assert len(loaded) == 1
    assert loaded[0].id == preset.id
    assert loaded[0].shortcut == "F8"
    assert loaded[0].root == preset.root


def test_active_filter_shortcuts_must_be_unique(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Filters")
    repository = ProjectFilterRepository(project.database_path)
    first = FilterPreset.create("First")
    second = FilterPreset.create("Second")
    first.shortcut = "Ctrl+1"
    second.shortcut = "ctrl+1"

    try:
        repository.save_presets([first, second])
    except ValueError as exc:
        assert "unikalne" in str(exc)
    else:
        raise AssertionError("duplicate active filter shortcuts were accepted")
