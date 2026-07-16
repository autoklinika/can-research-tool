from pathlib import Path

from app.live_message_buffer import LiveMessageBuffer
from app.logical_records import (
    LogicalMessageRecord,
    load_recent_logical_messages,
    logical_message_path_for_session,
)
from app.message_models import DecodedMessage, ProtocolKind, TransportKind, TransportMessage
from app.models import CanFrame, CaptureSession
from app.session_stream import SessionStreamWriter
from app.stream_exports import MessageCsvStreamWriter


def _record(sequence: int) -> LogicalMessageRecord:
    return LogicalMessageRecord(
        sequence=sequence,
        first_timestamp_ns=sequence * 1_000_000,
        last_timestamp_ns=sequence * 1_000_000,
        protocol="unknown",
        transport="raw",
        name="Raw CAN payload",
        arbitration_id=0x100 + sequence,
        is_extended_id=False,
        pgn=None,
        source_address=None,
        destination_address=None,
        complete=True,
        frame_sequences=(sequence,),
        payload=bytes([sequence]),
        fields={},
    )


def test_live_message_buffer_is_bounded() -> None:
    buffer = LiveMessageBuffer(capacity=2)
    buffer.append_many([_record(0), _record(1), _record(2)])

    snapshot = buffer.snapshot_since(None)
    assert [message.sequence for message in snapshot.messages] == [1, 2]
    assert snapshot.total_received == 3
    assert snapshot.dropped_from_view == 1


def test_load_recent_messages_from_csv(tmp_path: Path) -> None:
    session_path = tmp_path / "capture.crt.jsonl"
    with SessionStreamWriter(
        CaptureSession(name="capture", source="test"),
        session_path,
    ) as writer:
        writer.append(
            CanFrame(
                sequence=0,
                timestamp_ns=0,
                arbitration_id=0x123,
                data=b"\x01",
            )
        )

    decoded = DecodedMessage(
        message=TransportMessage(
            sequence=7,
            first_timestamp_ns=1_000_000,
            last_timestamp_ns=2_000_000,
            transport=TransportKind.J1939_BAM,
            payload=b"\xAA\xBB",
            frame_sequences=(1, 2, 3),
            arbitration_id=0x18ECFF30,
            is_extended_id=True,
            source_address=0x30,
            destination_address=0xFF,
            pgn=0xFECA,
        ),
        protocol=ProtocolKind.J1939,
        name="J1939 transported message",
        fields={"pgn": 0xFECA},
        confidence=0.9,
    )
    message_path = logical_message_path_for_session(session_path)
    with MessageCsvStreamWriter(message_path) as writer:
        writer.append(decoded)

    messages, total, source = load_recent_logical_messages(session_path, max_rows=10)
    assert source == "messages-csv"
    assert total == 1
    assert messages[0].sequence == 7
    assert messages[0].pgn == 0xFECA
    assert messages[0].payload == b"\xAA\xBB"
    assert messages[0].frame_sequences == (1, 2, 3)


def test_reconstruct_messages_when_csv_is_missing(tmp_path: Path) -> None:
    session_path = tmp_path / "raw.crt.jsonl"
    with SessionStreamWriter(
        CaptureSession(name="raw", source="test"),
        session_path,
    ) as writer:
        writer.append(
            CanFrame(
                sequence=0,
                timestamp_ns=0,
                arbitration_id=0x123,
                data=b"\x11\x22",
            )
        )

    messages, total, source = load_recent_logical_messages(session_path, max_rows=10)
    assert source == "reconstructed"
    assert total == 1
    assert messages[0].transport == "raw"
    assert messages[0].payload == b"\x11\x22"
    assert messages[0].frame_sequences == (0,)
