from __future__ import annotations

from app.filter_preferences import FilterCombinationMode
from app.filters import FilterMode, FilterPreset
from app.models import CanFrame
from app.static_active_filters import StaticCombinedActiveFilterSet
from app.static_filter_patterns import CanIdPattern, PayloadPattern
from app.static_frame_adapter import static_frame_record


def _preset(name: str, root: dict, *, mode: FilterMode = FilterMode.INCLUDE) -> FilterPreset:
    preset = FilterPreset.create(name)
    preset.mode = mode
    preset.root = root
    return preset


def _condition(field: str, operator: str, value: str) -> dict:
    return {
        "type": "condition",
        "field": field,
        "operator": operator,
        "values": [value],
    }


def test_shared_adapter_preserves_every_static_frame_field() -> None:
    frame = CanFrame(
        sequence=7,
        timestamp_ns=12_345_000,
        arbitration_id=0x18DAF900,
        data=bytes.fromhex("62 F1 90"),
        channel=3,
        is_extended_id=True,
        is_remote_frame=True,
        is_error_frame=True,
    )

    record = static_frame_record(frame)

    assert record.can_id == 0x18DAF900
    assert record.extended is True
    assert record.dlc == 3
    assert record.relative_time_us == 12_345
    assert record.channel == 3
    assert record.rtr is True
    assert record.error_frame is True
    assert record.payload == bytes.fromhex("62 F1 90")


def test_compiled_static_filter_matches_can_mask_payload_channel_and_flags() -> None:
    root = {
        "type": "group",
        "operator": "and",
        "children": [
            _condition("can_id", "can_id_pattern", "0x18DA??00"),
            _condition("payload", "payload_prefix", "62 F1 ??"),
            _condition("channel", "eq", "2"),
            _condition("rtr", "eq", "nie"),
            _condition("error_frame", "eq", "nie"),
        ],
    }
    filters = StaticCombinedActiveFilterSet([_preset("UDS raw", root)], scope="live")

    matching = CanFrame(
        sequence=1,
        timestamp_ns=1_000,
        arbitration_id=0x18DAF900,
        data=bytes.fromhex("62 F1 90 01"),
        channel=2,
        is_extended_id=True,
    )
    wrong_payload = CanFrame(
        sequence=2,
        timestamp_ns=2_000,
        arbitration_id=0x18DAF900,
        data=bytes.fromhex("7F 22 31"),
        channel=2,
        is_extended_id=True,
    )
    wrong_flag = CanFrame(
        sequence=3,
        timestamp_ns=3_000,
        arbitration_id=0x18DAF900,
        data=bytes.fromhex("62 F1 90"),
        channel=2,
        is_extended_id=True,
        is_error_frame=True,
    )

    assert filters.decide(static_frame_record(matching)).visible is True
    assert filters.decide(static_frame_record(wrong_payload)).visible is False
    assert filters.decide(static_frame_record(wrong_flag)).visible is False
    assert filters.affects_raw_visibility is True


def test_can_and_payload_patterns_are_not_reparsed_on_hot_path(monkeypatch) -> None:
    root = {
        "type": "group",
        "operator": "and",
        "children": [
            _condition("can_id", "can_id_pattern", "0x18DA??00"),
            _condition("payload", "payload_contains", "F1 ??"),
        ],
    }
    filters = StaticCombinedActiveFilterSet([_preset("Compiled", root)])

    def fail(*_args, **_kwargs):
        raise AssertionError("pattern parser must not run on the frame hot path")

    monkeypatch.setattr(CanIdPattern, "parse", fail)
    monkeypatch.setattr(PayloadPattern, "parse", fail)

    for sequence in range(10_000):
        frame = CanFrame(
            sequence=sequence,
            timestamp_ns=sequence * 1_000,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("62 F1 90"),
            is_extended_id=True,
        )
        assert filters.decide(static_frame_record(frame)).visible is True


def test_include_combination_mode_is_preserved_for_static_presets() -> None:
    first = _preset("ID", _condition("can_id", "can_id_pattern", "0x18DA??00"))
    second = _preset("Payload", _condition("payload", "payload_prefix", "62"))
    frame = static_frame_record(
        CanFrame(
            sequence=1,
            timestamp_ns=0,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("7F 22 31"),
            is_extended_id=True,
        )
    )

    and_filters = StaticCombinedActiveFilterSet(
        [first, second],
        combination_mode=FilterCombinationMode.AND,
    )
    or_filters = StaticCombinedActiveFilterSet(
        [first, second],
        combination_mode=FilterCombinationMode.OR,
    )

    assert and_filters.decide(frame).visible is False
    assert or_filters.decide(frame).visible is True


def test_static_raw_condition_is_neutral_for_logical_message_context() -> None:
    from app.logical_records import LogicalMessageRecord

    preset = _preset(
        "Raw payload",
        _condition("payload", "payload_exact", "62 F1 90"),
    )
    filters = StaticCombinedActiveFilterSet([preset])
    message = LogicalMessageRecord(
        sequence=1,
        first_timestamp_ns=0,
        last_timestamp_ns=1_000,
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
    )

    decision = filters.decide_logical_message(message)

    assert decision.visible is True
    assert decision.unavailable_reasons
