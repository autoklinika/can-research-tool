from __future__ import annotations

from app.logical_records import LogicalMessageRecord, reinterpret_raw_record
from app.protocols import ProtocolRegistry


def test_persisted_uds_record_is_reinterpreted_with_current_nrc_catalog() -> None:
    historical = LogicalMessageRecord(
        sequence=7,
        first_timestamp_ns=1_000,
        last_timestamp_ns=2_000,
        protocol="uds",
        transport="isotp",
        name="old UDS label",
        arbitration_id=0x18DAF930,
        is_extended_id=True,
        pgn=None,
        source_address=0x30,
        destination_address=0xF9,
        complete=True,
        frame_sequences=(10,),
        payload=bytes.fromhex("7F 27 35"),
        fields={"legacy": True},
    )

    current = reinterpret_raw_record(
        historical,
        base_registry=ProtocolRegistry(),
        dbc_decoder=None,
    )

    assert current.protocol == "uds"
    assert current.name != historical.name
    assert current.fields is not None
    assert current.fields["negative_response_name"] == "invalidKey"
    assert current.fields["requested_service_name"] == "SecurityAccess"


def test_persisted_raw_extended_record_is_reinterpreted_as_j1939() -> None:
    historical = LogicalMessageRecord(
        sequence=8,
        first_timestamp_ns=3_000,
        last_timestamp_ns=3_000,
        protocol="unknown",
        transport="raw",
        name="old unknown label",
        arbitration_id=0x18EA30F9,
        is_extended_id=True,
        pgn=0xEA00,
        source_address=0xF9,
        destination_address=0x30,
        complete=True,
        frame_sequences=(11,),
        payload=bytes.fromhex("00 EE 00 FF FF FF FF FF"),
        fields={},
    )

    current = reinterpret_raw_record(
        historical,
        base_registry=ProtocolRegistry(),
        dbc_decoder=None,
    )

    assert current.protocol == "j1939"
    assert current.fields is not None
    assert current.fields["pgn_name"] == "Request"
