from app.filters import CanFrameRecord, FilterMode, FilterPreset
from app.live_filters import ActiveFilterSet


def _preset(*, enabled: bool = True, scope: list[str] | None = None) -> FilterPreset:
    preset = FilterPreset.create("Only 0x100")
    preset.enabled = enabled
    preset.mode = FilterMode.INCLUDE
    preset.scope = list(scope or ["live", "stored_session"])
    preset.root = {
        "type": "group",
        "operator": "and",
        "children": [
            {
                "type": "condition",
                "field": "can_id",
                "operator": "eq",
                "values": ["0x100"],
            }
        ],
    }
    return preset


def test_disabled_preset_never_affects_live() -> None:
    filters = ActiveFilterSet([_preset(enabled=False)], scope="live")

    assert filters.active_count == 0
    assert filters.affects_visibility is False
    assert filters.decide(CanFrameRecord(0x200, False, 8)).visible is True


def test_stored_session_preset_never_affects_live() -> None:
    filters = ActiveFilterSet([_preset(scope=["stored_session"])], scope="live")

    assert filters.active_count == 0
    assert filters.decide(CanFrameRecord(0x200, False, 8)).visible is True


def test_live_preset_filters_only_when_selected_for_live_scope() -> None:
    filters = ActiveFilterSet([_preset(scope=["live"])], scope="live")

    assert filters.active_count == 1
    assert filters.decide(CanFrameRecord(0x100, False, 8)).visible is True
    assert filters.decide(CanFrameRecord(0x200, False, 8)).visible is False


def test_live_preset_is_not_available_to_stored_session_scope() -> None:
    filters = ActiveFilterSet([_preset(scope=["live"])], scope="stored_session")

    assert filters.active_count == 0
    assert filters.decide(CanFrameRecord(0x200, False, 8)).visible is True
