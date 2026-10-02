from app.models import CanFrame
from app.stream_pipeline import StreamingTransportPipeline


def _frame(sequence: int, can_id: int, data: str) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=sequence * 10_000_000,
        arbitration_id=can_id,
        data=bytes.fromhex(data),
        is_extended_id=True,
    )


def test_streaming_pipeline_keeps_tp_state_between_frames() -> None:
    pipeline = StreamingTransportPipeline()
    frames = [
        _frame(0, 0x18ECFF30, "20 22 00 05 FF CA FE 00"),
        _frame(1, 0x18EBFF30, "01 D7 FF 68 F9 E5 01 2E"),
        _frame(2, 0x18EBFF30, "02 00 01 CD 74 F9 E3 01"),
        _frame(3, 0x18EBFF30, "03 77 F9 E5 01 DB F7 E9"),
        _frame(4, 0x18EBFF30, "04 02 D9 F7 E9 02 DF F7"),
        _frame(5, 0x18EBFF30, "05 E9 01 DC F7 E9 02 FF"),
    ]

    messages = []
    for frame in frames:
        messages.extend(pipeline.feed(frame))

    assert len(messages) == 1
    message = messages[0]
    assert message.pgn == 0xFECA
    assert message.complete is True
    assert len(message.payload) == 34
    assert message.frame_sequences == (0, 1, 2, 3, 4, 5)
    assert pipeline.flush() == []


def test_orphan_j1939_frames_use_destination_to_pick_transport_kind() -> None:
    from app.message_models import TransportKind
    from app.models import CanFrame

    pipeline = StreamingTransportPipeline()
    payload = bytes([1, 1, 2, 3, 4, 5, 6, 7])
    abort = bytes([0xFF, 1, 0xFF, 0xFF, 0xFF, 0, 0xEF, 0])
    broadcast_dt = CanFrame(0, 0, 0x18EBFF00, payload, is_extended_id=True)
    peer_dt = CanFrame(1, 10, 0x18EB0201, payload, is_extended_id=True)
    peer_abort = CanFrame(2, 20, 0x18EC0201, abort, is_extended_id=True)

    messages = pipeline.feed_many([broadcast_dt, peer_dt, peer_abort])

    assert [message.transport for message in messages] == [
        TransportKind.J1939_BAM,
        TransportKind.J1939_RTS_CTS,
        TransportKind.J1939_RTS_CTS,
    ]
    assert all(not message.complete for message in messages)


def test_batch_pipeline_matches_streaming_feed_and_flush() -> None:
    from app.models import CanFrame
    from app.transport import TransportPipeline

    frames = [
        CanFrame(0, 0, 0x7E8, bytes([0x10, 0x0A, 1, 2, 3, 4, 5, 6]), channel=0),
        CanFrame(1, 100, 0x123, b"\x01", channel=0),
        CanFrame(2, 200, 0x7E8, bytes([0x21, 7, 8, 9, 10]), channel=0),
        CanFrame(3, 300, 0x7E0, bytes([0x10, 0x20, 1, 2, 3, 4, 5, 6]), channel=0),
    ]
    streaming = StreamingTransportPipeline()
    expected = sorted(
        streaming.feed_many(frames) + streaming.flush(),
        key=lambda item: (item.first_timestamp_ns, item.sequence),
    )

    assert TransportPipeline().process(frames) == expected
