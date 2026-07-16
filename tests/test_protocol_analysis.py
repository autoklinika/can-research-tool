from __future__ import annotations

from app.message_models import ProtocolKind, TransportKind, TransportMessage
from app.models import CanFrame
from app.protocols import ProtocolRegistry
from app.stream_pipeline import StreamingTransportPipeline


def _message(
    payload: bytes,
    *,
    transport: TransportKind = TransportKind.ISOTP,
    arbitration_id: int = 0x18DA30F9,
    extended: bool = True,
    pgn: int | None = None,
    source: int | None = 0xF9,
    destination: int | None = 0x30,
) -> TransportMessage:
    return TransportMessage(
        sequence=0,
        first_timestamp_ns=1_000,
        last_timestamp_ns=2_000,
        transport=transport,
        payload=payload,
        frame_sequences=(1,),
        arbitration_id=arbitration_id,
        is_extended_id=extended,
        source_address=source,
        destination_address=destination,
        pgn=pgn,
    )


def test_uds_request_exposes_service_direction_and_did() -> None:
    decoded = ProtocolRegistry().decode(_message(bytes.fromhex("22 F1 90")))

    assert decoded.protocol is ProtocolKind.UDS
    assert decoded.fields["direction"] == "request"
    assert decoded.fields["service_name"] == "ReadDataByIdentifier"
    assert decoded.fields["did"] == 0xF190
    assert decoded.fields["did_hex"] == "0xF190"
    assert "DID 0xF190" in decoded.name


def test_uds_negative_response_exposes_named_nrc() -> None:
    decoded = ProtocolRegistry().decode(_message(bytes.fromhex("7F 27 35")))

    assert decoded.protocol is ProtocolKind.UDS
    assert decoded.fields["direction"] == "negative-response"
    assert decoded.fields["requested_service_name"] == "SecurityAccess"
    assert decoded.fields["negative_response_code"] == 0x35
    assert decoded.fields["negative_response_name"] == "invalidKey"
    assert "invalidKey" in decoded.name


def test_uds_security_access_exposes_level_and_seed_key_phase() -> None:
    seed = ProtocolRegistry().decode(_message(bytes.fromhex("27 05")))
    key = ProtocolRegistry().decode(_message(bytes.fromhex("27 06 12 34")))

    assert seed.fields["security_level"] == 3
    assert seed.fields["security_access_type"] == "request-seed"
    assert key.fields["security_level"] == 3
    assert key.fields["security_access_type"] == "send-key"


def test_request_download_request_uses_data_and_address_length_formats() -> None:
    decoded = ProtocolRegistry().decode(
        _message(bytes.fromhex("34 00 44 00 A2 00 00 00 00 11 EE"))
    )

    assert decoded.protocol is ProtocolKind.UDS
    assert decoded.fields["response_type"] == "request"
    assert decoded.fields["data_format_identifier"] == 0x00
    assert decoded.fields["address_and_length_format_identifier"] == 0x44
    assert decoded.fields["memory_address_length"] == 4
    assert decoded.fields["memory_size_length"] == 4
    assert "length_format_identifier" not in decoded.fields


def test_request_download_positive_response_uses_max_block_length_format() -> None:
    decoded = ProtocolRegistry().decode(_message(bytes.fromhex("74 20 10 00")))

    assert decoded.protocol is ProtocolKind.UDS
    assert decoded.fields["response_type"] == "positive-response"
    assert decoded.fields["length_format_identifier"] == 0x20
    assert decoded.fields["max_number_of_block_length_size"] == 2
    assert decoded.fields["max_number_of_block_length"] == 0x1000
    assert "data_format_identifier" not in decoded.fields
    assert "address_and_length_format_identifier" not in decoded.fields


def test_raw_29bit_frame_remains_unknown_with_j1939_candidate_fields() -> None:
    # Priority 6, PF EA (Request), destination 0x30, source 0xF9. The identifier
    # can be parsed as J1939, but that alone does not prove the application protocol.
    decoded = ProtocolRegistry().decode(
        _message(
            bytes.fromhex("00 EE 00 FF FF FF FF FF"),
            transport=TransportKind.RAW,
            arbitration_id=0x18EA30F9,
            pgn=0xEA00,
        )
    )

    assert decoded.protocol is ProtocolKind.UNKNOWN
    candidate = decoded.fields["j1939_identifier_candidate"]
    assert candidate["pgn"] == 0xEA00
    assert candidate["pgn_name"] == "Request"
    assert candidate["priority"] == 6
    assert candidate["pdu_type"] == "PDU1"
    assert decoded.confidence == 0.0


def test_j1939_tp_application_message_uses_pgn_catalog() -> None:
    decoded = ProtocolRegistry().decode(
        _message(
            bytes.fromhex("01 02 03 04 05 06 07 08 09"),
            transport=TransportKind.J1939_BAM,
            arbitration_id=0x18ECFF30,
            pgn=0xFECA,
            source=0x30,
            destination=0xFF,
        )
    )

    assert decoded.protocol is ProtocolKind.J1939
    assert decoded.fields["pgn_name"] == "Active Diagnostic Trouble Codes (DM1)"
    assert decoded.fields["direction"] == "broadcast"
    assert "DM1" in decoded.name


def test_isotp_pipeline_reassembles_and_decodes_uds_positive_response() -> None:
    pipeline = StreamingTransportPipeline()
    frames = (
        CanFrame(
            sequence=0,
            timestamp_ns=1_000_000,
            arbitration_id=0x18DAF930,
            is_extended_id=True,
            data=bytes.fromhex("10 0A 62 F1 90 31 32 33"),
        ),
        CanFrame(
            sequence=1,
            timestamp_ns=2_000_000,
            arbitration_id=0x18DAF930,
            is_extended_id=True,
            data=bytes.fromhex("21 34 35 36 37 38 39 3A"),
        ),
    )

    messages = pipeline.feed_many(frames)
    assert len(messages) == 1
    message = messages[0]
    assert message.transport is TransportKind.ISOTP
    assert message.complete is True
    assert message.payload == bytes.fromhex("62 F1 90 31 32 33 34 35 36 37")
    assert message.frame_count == 2

    decoded = ProtocolRegistry().decode(message)
    assert decoded.protocol is ProtocolKind.UDS
    assert decoded.fields["direction"] == "positive-response"
    assert decoded.fields["did_hex"] == "0xF190"
