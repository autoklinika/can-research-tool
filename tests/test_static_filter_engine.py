from __future__ import annotations

from app.filters import FilterPreset, MatchState
from app.static_filter_engine import (
    StaticCanFrameRecord,
    StaticFilterCompiler,
    StaticFilterContext,
)


def _preset(*conditions: dict[str, object], operator: str = "and") -> FilterPreset:
    preset = FilterPreset.create("static-v2")
    preset.root = {
        "type": "group",
        "operator": operator,
        "children": list(conditions),
    }
    return preset


def _condition(field: str, operator: str, *values: object) -> dict[str, object]:
    return {
        "type": "condition",
        "field": field,
        "operator": operator,
        "values": list(values),
    }


def test_static_context_exposes_channel_flags_and_payload() -> None:
    frame = StaticCanFrameRecord(
        can_id=0x18DAF900,
        extended=True,
        dlc=8,
        channel=2,
        rtr=True,
        error_frame=False,
        payload=bytes.fromhex("62 F1 90 31 32 33"),
    )

    context = StaticFilterContext.from_frame(frame)

    assert context.resolve("channel") == (True, 2)
    assert context.resolve("rtr") == (True, True)
    assert context.resolve("error_frame") == (True, False)
    assert context.resolve("payload") == (True, bytes.fromhex("62 F1 90 31 32 33"))
    assert context.resolve("can_id") == (True, 0x18DAF900)


def test_channel_and_boolean_conditions() -> None:
    compiler = StaticFilterCompiler()
    preset = _preset(
        _condition("channel", "between", 1, 3),
        _condition("rtr", "eq", "tak"),
        _condition("error_frame", "eq", "nie"),
    )
    frame = StaticCanFrameRecord(
        can_id=0x123,
        extended=False,
        dlc=0,
        channel=2,
        rtr=True,
        error_frame=False,
    )

    assert compiler.evaluate(preset, frame).state == MatchState.MATCH


def test_can_id_wildcard_operator() -> None:
    compiler = StaticFilterCompiler()
    preset = _preset(_condition("can_id", "can_id_pattern", "0x18DA??F9"))

    assert (
        compiler.evaluate(
            preset,
            StaticCanFrameRecord(0x18DA00F9, True, 8),
        ).state
        == MatchState.MATCH
    )
    assert (
        compiler.evaluate(
            preset,
            StaticCanFrameRecord(0x18DAF900, True, 8),
        ).state
        == MatchState.NO_MATCH
    )


def test_payload_exact_prefix_and_contains_operators() -> None:
    compiler = StaticFilterCompiler()
    frame = StaticCanFrameRecord(
        can_id=0x7E8,
        extended=False,
        dlc=8,
        payload=bytes.fromhex("06 62 F1 90 31 32 33 00"),
    )

    exact = _preset(_condition("payload", "payload_exact", "06 62 F1 90 31 32 33 00"))
    prefix = _preset(_condition("payload", "payload_prefix", "06 62 ?? 90"))
    contains = _preset(_condition("payload", "payload_contains", "F1 90 31"))

    assert compiler.evaluate(exact, frame).state == MatchState.MATCH
    assert compiler.evaluate(prefix, frame).state == MatchState.MATCH
    assert compiler.evaluate(contains, frame).state == MatchState.MATCH


def test_payload_masked_byte_operator() -> None:
    compiler = StaticFilterCompiler()
    preset = _preset(_condition("payload", "payload_prefix", "A0/F0 55"))

    matching = StaticCanFrameRecord(0x123, False, 2, payload=bytes.fromhex("A7 55"))
    rejected = StaticCanFrameRecord(0x123, False, 2, payload=bytes.fromhex("97 55"))

    assert compiler.evaluate(preset, matching).state == MatchState.MATCH
    assert compiler.evaluate(preset, rejected).state == MatchState.NO_MATCH


def test_legacy_conditions_are_delegated_without_format_migration() -> None:
    compiler = StaticFilterCompiler()
    preset = _preset(
        _condition("can_id", "eq", "0x18DAF900"),
        _condition("dlc", "eq", 8),
    )
    frame = StaticCanFrameRecord(0x18DAF900, True, 8, channel=1)

    assert preset.format_version == 1
    assert compiler.validate(preset) == []
    assert compiler.evaluate(preset, frame).state == MatchState.MATCH


def test_mixed_legacy_and_v2_conditions_share_group_semantics() -> None:
    compiler = StaticFilterCompiler()
    preset = _preset(
        _condition("can_id", "eq", "0x18DAF900"),
        _condition("payload", "payload_contains", "7F 27 35"),
        _condition("channel", "eq", 0),
    )
    frame = StaticCanFrameRecord(
        0x18DAF900,
        True,
        8,
        channel=0,
        payload=bytes.fromhex("03 7F 27 35 00 00 00 00"),
    )

    assert compiler.evaluate(preset, frame).state == MatchState.MATCH


def test_invalid_static_condition_is_unavailable() -> None:
    compiler = StaticFilterCompiler()
    preset = _preset(_condition("payload", "payload_prefix", "GG"))
    frame = StaticCanFrameRecord(0x123, False, 1, payload=b"\x00")

    issues = compiler.validate(preset)
    result = compiler.evaluate(preset, frame)

    assert issues
    assert result.state == MatchState.UNAVAILABLE


def test_payload_and_channel_input_limits_are_enforced() -> None:
    try:
        StaticCanFrameRecord(0x123, False, 65, payload=b"\x00" * 65)
    except ValueError as exc:
        assert "DLC" in str(exc) or "64" in str(exc)
    else:
        raise AssertionError("invalid frame was accepted")

    try:
        StaticCanFrameRecord(0x123, False, 1, channel=-1, payload=b"\x00")
    except ValueError as exc:
        assert "channel" in str(exc)
    else:
        raise AssertionError("negative channel was accepted")
