from app.custom_rules import MessageRule
from app.j1939 import decode_j1939_identifier
from app.message_analysis import LogicalMessageAnalyzer
from app.message_models import ProtocolKind, TransportKind
from app.models import CanFrame
from app.protocols import ProtocolRegistry
from app.transport import TransportPipeline


def frame(
    sequence: int,
    timestamp_ms: int,
    can_id: int,
    data: str,
    *,
    extended: bool = True,
) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ms * 1_000_000,
        arbitration_id=can_id,
        data=bytes.fromhex(data),
        is_extended_id=extended,
    )


def test_decodes_j1939_identifier_without_claiming_protocol() -> None:
    identifier = decode_j1939_identifier(0x18ECFF30)

    assert identifier.priority == 6
    assert identifier.pdu_format == 0xEC
    assert identifier.destination_address == 0xFF
    assert identifier.source_address == 0x30
    assert identifier.pgn == 0xEC00


def test_reassembles_j1939_bam_and_classifies_single_frame_j1939() -> None:
    frames = [
        frame(0, 0, 0x18ECFF30, "20 0A 00 02 FF CA FE 00"),
        frame(1, 10, 0x18EBFF30, "01 01 02 03 04 05 06 07"),
        frame(2, 20, 0x18EBFF30, "02 08 09 0A FF FF FF FF"),
        frame(3, 1000, 0x18FEAE30, "FF FF 00 00 FF FF FF FF"),
    ]

    transport_messages = TransportPipeline().process(frames)
    decoded = ProtocolRegistry().decode_all(transport_messages)

    assert len(decoded) == 2

    tp_message = next(
        item for item in decoded if item.message.transport is TransportKind.J1939_BAM
    )
    assert tp_message.protocol is ProtocolKind.J1939
    assert tp_message.message.pgn == 0xFECA
    assert tp_message.message.source_address == 0x30
    assert tp_message.message.destination_address == 0xFF
    assert tp_message.message.payload == bytes(range(1, 11))
    assert tp_message.message.complete is True
    assert tp_message.message.frame_count == 3

    single_frame = next(
        item for item in decoded if item.message.transport is TransportKind.RAW
    )
    assert single_frame.protocol is ProtocolKind.J1939
    assert single_frame.message.arbitration_id == 0x18FEAE30
    assert single_frame.fields["classification_basis"] == "29-bit J1939 identifier layout"
    assert single_frame.fields["pgn"] == 0xFEAE


def test_reassembles_29bit_isotp_and_decodes_uds() -> None:
    frames = [
        frame(0, 0, 0x18DA30F9, "03 22 F1 90 00 00 00 00"),
        frame(1, 100, 0x18DAF930, "10 0A 62 F1 90 41 42 43"),
        frame(2, 110, 0x18DAF930, "21 44 45 46 47 FF FF FF"),
    ]

    decoded = ProtocolRegistry().decode_all(TransportPipeline().process(frames))

    assert len(decoded) == 2
    request = decoded[0]
    response = decoded[1]

    assert request.protocol is ProtocolKind.UDS
    assert request.message.transport is TransportKind.ISOTP
    assert request.message.source_address == 0xF9
    assert request.message.destination_address == 0x30
    assert request.fields["service_name"] == "ReadDataByIdentifier"
    assert request.fields["did"] == 0xF190
    assert request.fields["response_type"] == "request"

    assert response.protocol is ProtocolKind.UDS
    assert response.message.payload == b"\x62\xF1\x90ABCDEFG"
    assert response.message.source_address == 0x30
    assert response.message.destination_address == 0xF9
    assert response.fields["response_type"] == "positive-response"
    assert response.fields["did"] == 0xF190


def test_marks_incomplete_isotp_at_end_of_capture() -> None:
    frames = [
        frame(0, 0, 0x18DAF930, "10 0A 62 F1 90 41 42 43"),
    ]

    decoded = ProtocolRegistry().decode_all(TransportPipeline().process(frames))

    assert len(decoded) == 1
    assert decoded[0].protocol is ProtocolKind.UDS
    assert decoded[0].message.complete is False
    assert "capture ended" in decoded[0].message.error


def test_logical_statistics_use_reassembled_message_period() -> None:
    frames = [
        frame(0, 0, 0x18ECFF30, "20 0A 00 02 FF CA FE 00"),
        frame(1, 10, 0x18EBFF30, "01 01 02 03 04 05 06 07"),
        frame(2, 20, 0x18EBFF30, "02 08 09 0A FF FF FF FF"),
        frame(3, 1000, 0x18ECFF30, "20 0A 00 02 FF CA FE 00"),
        frame(4, 1010, 0x18EBFF30, "01 01 02 03 04 05 06 07"),
        frame(5, 1020, 0x18EBFF30, "02 08 09 0A FF FF FF FF"),
    ]

    decoded = ProtocolRegistry().decode_all(TransportPipeline().process(frames))
    statistics = LogicalMessageAnalyzer().summarize(decoded)

    assert len(statistics) == 1
    assert statistics[0].message_count == 2
    assert statistics[0].mean_period_ms == 1000.0
    assert statistics[0].estimated_frequency_hz == 1.0


def test_custom_rule_marks_proprietary_frame_without_forcing_j1939() -> None:
    frames = [
        frame(0, 0, 0x18FF5230, "A5 01 02 03 04 05 06 07"),
    ]
    messages = TransportPipeline().process(frames)
    decoded = ProtocolRegistry(
        custom_rules=[
            MessageRule(
                name="Vendor status frame",
                arbitration_id=0x18FF5200,
                arbitration_mask=0x1FFFFF00,
                is_extended_id=True,
                transport=TransportKind.RAW,
            )
        ]
    ).decode_all(messages)

    assert len(decoded) == 1
    assert decoded[0].protocol is ProtocolKind.PROPRIETARY
    assert decoded[0].name == "Vendor status frame"


def test_unknown_isotp_payload_is_not_forced_to_uds() -> None:
    frames = [
        frame(0, 0, 0x18DA30F9, "03 A5 01 02 00 00 00 00"),
    ]

    decoded = ProtocolRegistry().decode_all(TransportPipeline().process(frames))

    assert len(decoded) == 1
    assert decoded[0].message.transport is TransportKind.ISOTP
    assert decoded[0].protocol is ProtocolKind.UNKNOWN
