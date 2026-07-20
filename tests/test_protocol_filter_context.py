from __future__ import annotations

from app.filters import (
    CanFrameRecord,
    FilterCompiler,
    FilterContext,
    FilterPreset,
    MatchState,
)
from app.logical_records import LogicalMessageRecord


def _preset(name: str, *conditions: dict[str, object]) -> FilterPreset:
    preset = FilterPreset.create(name)
    preset.root = {
        "type": "group",
        "operator": "and",
        "children": list(conditions),
    }
    return preset


def _condition(field: str, value: object, operator: str = "eq") -> dict[str, object]:
    return {
        "type": "condition",
        "field": field,
        "operator": operator,
        "values": [value],
    }


def _logical_record(
    *,
    protocol: str = "uds",
    transport: str = "isotp",
    pgn: int | None = None,
    fields: dict[str, object] | None = None,
) -> LogicalMessageRecord:
    return LogicalMessageRecord(
        sequence=7,
        first_timestamp_ns=1_000_000_000,
        last_timestamp_ns=1_010_000_000,
        protocol=protocol,
        transport=transport,
        name="UDS POS 0x62 ReadDataByIdentifier",
        arbitration_id=0x18DAF110,
        is_extended_id=True,
        pgn=pgn,
        source_address=0xF1,
        destination_address=0x10,
        complete=True,
        frame_sequences=(100, 101, 102),
        payload=bytes.fromhex("62 F1 90"),
        confidence=0.99,
        fields=fields or {},
    )


def test_logical_uds_fields_use_the_global_filter_compiler() -> None:
    record = _logical_record(
        fields={
            "service_id": 0x62,
            "base_service_id": 0x22,
            "direction": "positive-response",
            "did": 0xF190,
        }
    )
    preset = _preset(
        "UDS F190",
        _condition("protocol", "UDS"),
        _condition("transport", "ISOtp"),
        _condition("complete", "yes"),
        _condition("confidence", 0.9, "ge"),
        _condition("source_frame_count", 3),
        _condition("source_address", "0xF1"),
        _condition("destination_address", "0x10"),
        _condition("sid", "0x62"),
        _condition("base_sid", "0x22"),
        _condition("direction", "positive-response"),
        _condition("did", "0xF190"),
    )
    compiler = FilterCompiler()

    assert compiler.validate(preset) == []
    assert (
        compiler.evaluate_logical_message(
            preset,
            record,
            relative_time_us=1_000_000,
        ).state
        is MatchState.MATCH
    )


def test_j1939_context_exposes_pgn_and_addresses() -> None:
    record = _logical_record(
        protocol="j1939",
        transport="j1939_bam",
        pgn=0xFECA,
        fields={"direction": "broadcast"},
    )
    preset = _preset(
        "DM1",
        _condition("protocol", "j1939"),
        _condition("transport", "j1939_bam"),
        _condition("pgn", "0xFECA"),
        _condition("source_address", "0xF1"),
        _condition("direction", "broadcast"),
    )

    result = FilterCompiler().evaluate_context(
        preset,
        FilterContext.from_logical_message(record),
    )

    assert result.state is MatchState.MATCH


def test_negative_response_uses_requested_sid_as_base_sid() -> None:
    record = _logical_record(
        fields={
            "service_id": 0x7F,
            "requested_service_id": 0x22,
            "negative_response_code": 0x31,
            "direction": "negative-response",
        }
    )
    preset = _preset(
        "UDS negative",
        _condition("sid", "0x7F"),
        _condition("base_sid", "0x22"),
        _condition("nrc", "0x31"),
        _condition("direction", "negative-response"),
    )

    assert FilterCompiler().evaluate_logical_message(preset, record).state is MatchState.MATCH


def test_missing_logical_field_returns_unavailable_without_crashing() -> None:
    record = _logical_record(fields={})
    preset = _preset("Missing RID", _condition("routine_id", "0x1234"))

    result = FilterCompiler().evaluate_logical_message(preset, record)

    assert result.state is MatchState.UNAVAILABLE
    assert "routine_id" in result.reason


def test_existing_raw_frame_evaluation_remains_compatible() -> None:
    preset = _preset("Raw", _condition("can_id", "0x123"))

    result = FilterCompiler().evaluate(
        preset,
        CanFrameRecord(can_id=0x123, extended=False, dlc=8),
    )

    assert result.state is MatchState.MATCH


def test_extended_uds_context_exposes_gui_filter_fields() -> None:
    record = _logical_record(
        fields={
            "service_id": 0x67,
            "base_service_id": 0x27,
            "direction": "positive-response",
            "response_type": "positive-response",
            "service_name": "SecurityAccess",
            "subfunction": 0x05,
            "suppress_positive_response": True,
            "security_access_type": "request-seed",
            "security_level": 3,
            "block_sequence_counter": 0x7A,
            "addressing": "normal-fixed-29bit",
        }
    )
    preset = _preset(
        "UDS GUI fields",
        _condition("addressing", "normal-fixed-29bit"),
        _condition("isotp_framing", "multi-frame"),
        _condition("isotp_has_error", False),
        _condition("response_type", "positive-response"),
        _condition("service_name", "SecurityAccess"),
        _condition("suppress_positive_response", True),
        _condition("security_access_type", "request-seed"),
        _condition("security_level", 3),
        _condition("block_sequence_counter", "0x7A"),
    )

    result = FilterCompiler().evaluate_logical_message(preset, record)

    assert result.state is MatchState.MATCH


def test_extended_uds_numeric_bounds_are_validated() -> None:
    invalid_level = _preset("Bad level", _condition("security_level", 64))
    invalid_counter = _preset("Bad counter", _condition("block_sequence_counter", 256))
    invalid_subfunction = _preset("Bad subfunction", _condition("subfunction", 128))

    compiler = FilterCompiler()

    assert compiler.validate(invalid_level)
    assert compiler.validate(invalid_counter)
    assert compiler.validate(invalid_subfunction)
