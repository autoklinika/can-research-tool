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


def test_protocol_only_include_is_neutral_for_raw_frame_view() -> None:
    item = FilterPreset.create("Only UDS")
    item.mode = FilterMode.INCLUDE
    item.root = {
        "type": "condition",
        "field": "protocol",
        "operator": "eq",
        "values": ["uds"],
    }
    filters = ActiveFilterSet([item])

    decision = filters.decide(frame(0x123))

    assert decision.visible is True
    assert decision.unavailable_reasons


def test_logical_message_decision_uses_protocol_context() -> None:
    from app.logical_records import LogicalMessageRecord

    item = FilterPreset.create("UDS F190")
    item.mode = FilterMode.INCLUDE
    item.root = {
        "type": "group",
        "operator": "and",
        "children": [
            {
                "type": "condition",
                "field": "protocol",
                "operator": "eq",
                "values": ["uds"],
            },
            {
                "type": "condition",
                "field": "did",
                "operator": "eq",
                "values": ["0xF190"],
            },
        ],
    }
    filters = ActiveFilterSet([item])
    matching = LogicalMessageRecord(
        sequence=1,
        first_timestamp_ns=1_000,
        last_timestamp_ns=2_000,
        protocol="uds",
        transport="isotp",
        name="ReadDataByIdentifier",
        arbitration_id=0x7E8,
        is_extended_id=False,
        pgn=None,
        source_address=None,
        destination_address=None,
        complete=True,
        frame_sequences=(1,),
        payload=bytes.fromhex("62 F1 90"),
        fields={"did": 0xF190},
    )
    other = LogicalMessageRecord(
        sequence=2,
        first_timestamp_ns=2_000,
        last_timestamp_ns=3_000,
        protocol="j1939",
        transport="raw",
        name="J1939",
        arbitration_id=0x18FEEE30,
        is_extended_id=True,
        pgn=0xFEEE,
        source_address=0x30,
        destination_address=None,
        complete=True,
        frame_sequences=(2,),
        payload=b"\x00" * 8,
        fields={},
    )

    assert filters.decide_logical_message(matching).visible is True
    assert filters.decide_logical_message(other).visible is False


def test_raw_hot_path_does_not_revalidate_or_reparse_presets(monkeypatch) -> None:
    item = FilterPreset.create("Fast raw")
    item.mode = FilterMode.INCLUDE
    item.root = {
        "type": "group",
        "operator": "and",
        "children": [
            condition("0x18DAF900"),
            {
                "type": "condition",
                "field": "dlc",
                "operator": "between",
                "values": ["0", "8"],
            },
        ],
    }
    filters = ActiveFilterSet([item])

    def fail(*_args, **_kwargs):
        raise AssertionError("raw hot path must use the compiled preset")

    monkeypatch.setattr(filters._compiler, "validate", fail)
    monkeypatch.setattr(filters._compiler, "_normalize_value", fail)

    for index in range(10_000):
        decision = filters.decide(
            CanFrameRecord(
                can_id=0x18DAF900 if index % 2 == 0 else 0x123,
                extended=True,
                dlc=8,
                relative_time_us=index,
            )
        )
        assert decision.visible is (index % 2 == 0)


def test_protocol_only_filter_does_not_request_raw_buffer_scan() -> None:
    item = FilterPreset.create("Only UDS")
    item.mode = FilterMode.INCLUDE
    item.root = {
        "type": "condition",
        "field": "did",
        "operator": "eq",
        "values": ["0xF190"],
    }

    assert ActiveFilterSet([item]).affects_raw_visibility is False
    assert ActiveFilterSet([preset("Raw", FilterMode.INCLUDE, "0x123")]).affects_raw_visibility is True
