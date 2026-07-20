from __future__ import annotations

from pathlib import Path

from app.combined_filters import CombinedActiveFilterSet
from app.filter_preferences import FilterCombinationMode, ProjectFilterPreferences
from app.filters import CanFrameRecord, FilterMode, FilterPreset


def _include(name: str, field: str, value: str) -> FilterPreset:
    preset = FilterPreset.create(name)
    preset.enabled = True
    preset.mode = FilterMode.INCLUDE
    preset.root = {
        "type": "condition",
        "field": field,
        "operator": "eq",
        "values": [value],
    }
    return preset


def test_include_presets_support_and_or() -> None:
    presets = [
        _include("CAN 0x100", "can_id", "0x100"),
        _include("DLC 8", "dlc", "8"),
    ]
    one_match = CanFrameRecord(can_id=0x100, extended=False, dlc=7)
    both_match = CanFrameRecord(can_id=0x100, extended=False, dlc=8)
    no_match = CanFrameRecord(can_id=0x200, extended=False, dlc=7)

    and_set = CombinedActiveFilterSet(
        presets,
        scope="live",
        combination_mode=FilterCombinationMode.AND,
    )
    or_set = CombinedActiveFilterSet(
        presets,
        scope="live",
        combination_mode=FilterCombinationMode.OR,
    )

    assert and_set.decide(one_match).visible is False
    assert and_set.decide(both_match).visible is True
    assert or_set.decide(one_match).visible is True
    assert or_set.decide(no_match).visible is False
    assert and_set.signature != or_set.signature


def test_exclude_remains_hide_on_any_match() -> None:
    include = _include("CAN 0x100", "can_id", "0x100")
    exclude = _include("Hide DLC 8", "dlc", "8")
    exclude.mode = FilterMode.EXCLUDE
    filter_set = CombinedActiveFilterSet(
        [include, exclude],
        scope="live",
        combination_mode=FilterCombinationMode.OR,
    )

    assert filter_set.decide(CanFrameRecord(0x100, False, 8)).visible is False
    assert filter_set.decide(CanFrameRecord(0x100, False, 7)).visible is True


def test_project_combination_preference_persists(tmp_path: Path) -> None:
    database = tmp_path / "project.sqlite"
    preferences = ProjectFilterPreferences(database)

    assert preferences.combination_mode() is FilterCombinationMode.AND
    preferences.set_combination_mode(FilterCombinationMode.OR)
    assert ProjectFilterPreferences(database).combination_mode() is FilterCombinationMode.OR
