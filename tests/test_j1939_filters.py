from __future__ import annotations

from app.filters import FilterCompiler, FilterContext, FilterPreset, MatchState
from app.logical_records import LogicalMessageRecord


def _condition(field: str, value: object, operator: str = "eq") -> dict[str, object]:
    return {
        "type": "condition",
        "field": field,
        "operator": operator,
        "values": [value],
    }


def _preset(name: str, *conditions: dict[str, object]) -> FilterPreset:
    preset = FilterPreset.create(name)
    preset.root = {
        "type": "group",
        "operator": "and",
        "children": list(conditions),
    }
    return preset


def _record(
    *,
    protocol: str = "j1939",
    transport: str = "raw",
    arbitration_id: int | None = 0x18FEEE30,
    pgn: int | None = 0xFEEE,
    source: int | None = 0x30,
    destination: int | None = None,
    complete: bool = True,
    payload: bytes = bytes.fromhex("01 02 03 04 05 06 07 08"),
    frame_sequences: tuple[int, ...] = (1,),
    fields: dict[str, object] | None = None,
) -> LogicalMessageRecord:
    return LogicalMessageRecord(
        sequence=1,
        first_timestamp_ns=1_000_000,
        last_timestamp_ns=2_000_000,
        protocol=protocol,
        transport=transport,
        name="J1939 message",
        arbitration_id=arbitration_id,
        is_extended_id=True,
        pgn=pgn,
        source_address=source,
        destination_address=destination,
        complete=complete,
        frame_sequences=frame_sequences,
        payload=payload,
        confidence=1.0,
        fields=fields or {},
    )


def test_confirmed_single_frame_j1939_exposes_identifier_layout() -> None:
    record = _record()
    preset = _preset(
        "PDU2",
        _condition("protocol", "j1939"),
        _condition("priority", 6),
        _condition("extended_data_page", 0),
        _condition("data_page", 0),
        _condition("pdu_format", "0xFE"),
        _condition("pdu_specific", "0xEE"),
        _condition("pdu_type", "PDU2"),
        _condition("broadcast", "yes"),
        _condition("destination_specific", "no"),
        _condition("j1939_transport", "single-frame"),
        _condition("j1939_is_tp", False),
        _condition("payload_length", 8),
    )

    result = FilterCompiler().evaluate_logical_message(preset, record)

    assert result.state is MatchState.MATCH


def test_pdu1_destination_specific_fields_use_destination_address() -> None:
    record = _record(
        arbitration_id=0x18EA3031,
        pgn=0xEA00,
        source=0x31,
        destination=0x30,
    )
    preset = _preset(
        "Request to 0x30",
        _condition("pdu_type", "pdu1"),
        _condition("pdu_format", "0xEA"),
        _condition("pdu_specific", "0x30"),
        _condition("broadcast", False),
        _condition("destination_specific", True),
    )

    assert FilterCompiler().evaluate_logical_message(preset, record).state is MatchState.MATCH


def test_bam_filter_exposes_transport_packet_and_payload_metadata() -> None:
    record = _record(
        transport="j1939-bam",
        arbitration_id=None,
        pgn=0xFECA,
        destination=0xFF,
        payload=bytes(range(20)),
        frame_sequences=(10, 11, 12, 13),
        fields={
            "pgn_name": "Active Diagnostic Trouble Codes (DM1)",
            "declared_payload_length": 20,
            "declared_packet_count": 3,
            "received_packet_count": 3,
        },
    )
    preset = _preset(
        "BAM DM1",
        _condition("pgn", "0xFECA"),
        _condition("pgn_name", "active diagnostic trouble codes (dm1)"),
        _condition("pdu_type", "pdu2"),
        _condition("broadcast", True),
        _condition("j1939_transport", "J1939_BAM"),
        _condition("j1939_is_tp", True),
        _condition("complete", True),
        _condition("declared_packet_count", 3),
        _condition("received_packet_count", 3),
        _condition("declared_payload_length", 20),
        _condition("received_payload_length", 20),
        _condition("source_frame_count", 4),
    )

    result = FilterCompiler().evaluate_context(
        preset,
        FilterContext.from_logical_message(record),
    )

    assert result.state is MatchState.MATCH


def test_rts_cts_alias_is_normalized() -> None:
    record = _record(
        transport="j1939-rts-cts",
        arbitration_id=None,
        pgn=0xEF00,
        destination=0x44,
    )
    preset = _preset("RTS CTS", _condition("j1939_transport", "RTS/CTS"))

    assert FilterCompiler().evaluate_logical_message(preset, record).state is MatchState.MATCH


def test_unknown_29bit_candidate_does_not_expose_j1939_specific_fields() -> None:
    record = _record(
        protocol="unknown",
        fields={
            "j1939_identifier_candidate": {
                "priority": 6,
                "pdu_type": "PDU2",
            }
        },
    )
    preset = _preset("Candidate", _condition("priority", 6))

    result = FilterCompiler().evaluate_logical_message(preset, record)

    assert result.state is MatchState.UNAVAILABLE
    assert "priority" in result.reason


def test_j1939_priority_validation_rejects_values_above_seven() -> None:
    preset = _preset("Invalid priority", _condition("priority", 8))

    issues = FilterCompiler().validate(preset)

    assert len(issues) == 1
    assert "0–7" in issues[0].message
