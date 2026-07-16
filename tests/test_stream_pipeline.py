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
