from __future__ import annotations

from app.message_models import TransportKind, TransportMessage
from app.models import CanFrame
from app.protocols import ProtocolRegistry
from app.stream_pipeline import StreamingTransportPipeline
from app.uds import UdsDecoder


def _message(payload: bytes) -> TransportMessage:
    return TransportMessage(
        sequence=0,
        first_timestamp_ns=0,
        last_timestamp_ns=0,
        transport=TransportKind.ISOTP,
        payload=payload,
        frame_sequences=(0,),
        arbitration_id=0x18DAF900,
        is_extended_id=True,
        source_address=0x00,
        destination_address=0xF9,
    )


def _decode(payload: bytes):
    return UdsDecoder().decode(_message(payload))


def test_read_data_by_identifier_response_exposes_vin_record() -> None:
    vin = b"XLRTE47MS0E123456"
    decoded = _decode(b"\x62\xF1\x90" + vin)

    assert decoded.protocol.value == "uds"
    assert decoded.name == "UDS POS 0x62 ReadDataByIdentifier DID 0xF190"
    assert decoded.fields["did"] == 0xF190
    assert decoded.fields["did_hex"] == "0xF190"
    assert decoded.fields["data_record_length"] == len(vin)
    assert decoded.fields["data_record_ascii"] == vin.decode("ascii")
    assert decoded.fields["data_record_hex"].startswith("58 4C 52")


def test_multiframe_isotp_vin_is_reassembled_before_uds_decode() -> None:
    pipeline = StreamingTransportPipeline()
    frames = (
        CanFrame(
            sequence=0,
            timestamp_ns=0,
            arbitration_id=0x18DAF900,
            is_extended_id=True,
            data=bytes.fromhex("10 14 62 F1 90 58 4C 52"),
        ),
        CanFrame(
            sequence=1,
            timestamp_ns=1_000_000,
            arbitration_id=0x18DAF900,
            is_extended_id=True,
            data=bytes.fromhex("21 54 45 34 37 4D 53 30"),
        ),
        CanFrame(
            sequence=2,
            timestamp_ns=2_000_000,
            arbitration_id=0x18DAF900,
            is_extended_id=True,
            data=bytes.fromhex("22 45 31 32 33 34 35 36"),
        ),
    )

    messages = []
    for frame in frames:
        messages.extend(pipeline.feed(frame))

    assert len(messages) == 1
    assert messages[0].transport is TransportKind.ISOTP
    assert messages[0].payload == b"\x62\xF1\x90XLRTE47MS0E123456"
    decoded = ProtocolRegistry().decode(messages[0])
    assert decoded.fields["did_hex"] == "0xF190"
    assert decoded.fields["data_record_ascii"] == "XLRTE47MS0E123456"


def test_read_data_by_identifier_request_lists_all_dids() -> None:
    decoded = _decode(bytes.fromhex("22 F1 90 F1 88 F1 92"))

    assert decoded.fields["did_count"] == 3
    assert decoded.fields["did_list"] == [0xF190, 0xF188, 0xF192]
    assert decoded.fields["did_list_hex"] == "0xF190, 0xF188, 0xF192"


def test_diagnostic_session_positive_response_decodes_timing() -> None:
    decoded = _decode(bytes.fromhex("50 01 00 32 00 FA"))

    assert decoded.fields["diagnostic_session_type"] == 0x01
    assert decoded.fields["p2_server_max_ms"] == 50
    assert decoded.fields["p2_star_server_max_ms"] == 2500


def test_security_access_seed_and_key_are_not_lost() -> None:
    seed = _decode(bytes.fromhex("67 07 5A 19 4C 00"))
    key = _decode(bytes.fromhex("27 08 A1 74 97 E5"))

    assert seed.fields["security_access_type"] == "request-seed"
    assert seed.fields["security_level"] == 4
    assert seed.fields["seed_hex"] == "5A 19 4C 00"
    assert key.fields["security_access_type"] == "send-key"
    assert key.fields["security_level"] == 4
    assert key.fields["key_hex"] == "A1 74 97 E5"


def test_request_download_decodes_address_and_size() -> None:
    decoded = _decode(bytes.fromhex("34 00 44 00 A2 00 00 00 00 11 EE"))

    assert decoded.fields["data_format_identifier"] == 0x00
    assert decoded.fields["memory_address_length"] == 4
    assert decoded.fields["memory_size_length"] == 4
    assert decoded.fields["memory_address"] == 0x00A20000
    assert decoded.fields["memory_address_hex"] == "0x00A20000"
    assert decoded.fields["memory_size"] == 0x11EE
    assert decoded.fields["memory_size_hex"] == "0x000011EE"


def test_request_download_positive_response_decodes_block_length() -> None:
    decoded = _decode(bytes.fromhex("74 20 0F E2"))

    assert decoded.fields["max_number_of_block_length_size"] == 2
    assert decoded.fields["max_number_of_block_length"] == 0x0FE2


def test_transfer_data_decodes_block_and_payload() -> None:
    request = _decode(bytes.fromhex("36 03 DE AD BE EF"))
    response = _decode(bytes.fromhex("76 03 01 02"))

    assert request.fields["block_sequence_counter"] == 3
    assert request.fields["transfer_data_hex"] == "DE AD BE EF"
    assert response.fields["block_sequence_counter"] == 3
    assert response.fields["transfer_response_parameter_record_hex"] == "01 02"


def test_routine_control_decodes_routine_record() -> None:
    request = _decode(bytes.fromhex("31 01 F0 22 00 A0 00 00"))
    response = _decode(bytes.fromhex("71 01 F0 22 00"))

    assert request.fields["routine_id"] == 0xF022
    assert request.fields["routine_option_record_hex"] == "00 A0 00 00"
    assert response.fields["routine_id"] == 0xF022
    assert response.fields["routine_status_record_hex"] == "00"


def test_negative_response_decodes_nrc_and_pending_flag() -> None:
    invalid_key = _decode(bytes.fromhex("7F 27 35"))
    pending = _decode(bytes.fromhex("7F 36 78"))

    assert invalid_key.fields["requested_service_name"] == "SecurityAccess"
    assert invalid_key.fields["negative_response_code_hex"] == "0x35"
    assert invalid_key.fields["negative_response_name"] == "invalidKey"
    assert invalid_key.fields["response_pending"] is False
    assert pending.fields["response_pending"] is True


def test_read_dtc_response_decodes_common_four_byte_entries() -> None:
    decoded = _decode(bytes.fromhex("59 02 FF 12 34 56 2F AB CD EF 08"))

    assert decoded.fields["dtc_status_availability_mask"] == 0xFF
    assert decoded.fields["dtc_count"] == 2
    assert decoded.fields["dtc_entries"][0] == {
        "dtc": 0x123456,
        "dtc_hex": "0x123456",
        "status": 0x2F,
        "status_hex": "0x2F",
    }
    assert decoded.fields["dtc_summary"] == "0x123456/0x2F, 0xABCDEF/0x08"
