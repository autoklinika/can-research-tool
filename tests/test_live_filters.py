from app.filters import CanFrameRecord, FilterMode, FilterPreset
from app.live_filters import ActiveFilterSet


def condition(can_id: str) -> dict:
    return {
        "type": "condition",
        "field": "can_id",
        "operator": "eq",
        "values": [can_id],
    }


def preset(name: str, mode: FilterMode, can_id: str) -> FilterPreset:
    item = FilterPreset.create(name)
    item.mode = mode
    item.root = condition(can_id)
    return item


def frame(can_id: int) -> CanFrameRecord:
    return CanFrameRecord(can_id=can_id, extended=True, dlc=8)


def test_include_filter_hides_non_matching_frames() -> None:
    filters = ActiveFilterSet([preset("EGR", FilterMode.INCLUDE, "0x18FEAE30")])

    assert filters.decide(frame(0x18FEAE30)).visible is True
    assert filters.decide(frame(0x18DAF900)).visible is False


def test_multiple_include_filters_use_and_semantics() -> None:
    first = preset("A", FilterMode.INCLUDE, "0x100")
    second = preset("B", FilterMode.INCLUDE, "0x200")
    filters = ActiveFilterSet([first, second])

    assert filters.decide(frame(0x100)).visible is False
    assert filters.decide(frame(0x200)).visible is False


def test_exclude_filter_removes_matching_frames() -> None:
    filters = ActiveFilterSet([preset("Ukryj", FilterMode.EXCLUDE, "0x123")])

    assert filters.decide(frame(0x123)).visible is False
    assert filters.decide(frame(0x124)).visible is True


def test_highlight_filter_does_not_hide_frames() -> None:
    filters = ActiveFilterSet([preset("Wyróżnij", FilterMode.HIGHLIGHT, "0x321")])

    matching = filters.decide(frame(0x321))
    other = filters.decide(frame(0x322))
    assert matching.visible is True and matching.highlighted is True
    assert other.visible is True and other.highlighted is False


def test_disabled_filter_is_ignored() -> None:
    item = preset("Wyłączony", FilterMode.INCLUDE, "0x555")
    item.enabled = False
    filters = ActiveFilterSet([item])

    assert filters.active_count == 0
    assert filters.decide(frame(0x111)).visible is True
