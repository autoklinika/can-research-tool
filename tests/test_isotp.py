from crt.isotp import PassiveIsoTpReassembler
from crt.models import CanFrame


def frame(timestamp: float, can_id: int, data: bytes) -> CanFrame:
    return CanFrame(timestamp_s=timestamp, arbitration_id=can_id, data=data)


def test_reassembles_multiframe_vin_response() -> None:
    reassembler = PassiveIsoTpReassembler()
    can_id = 0x18DAF930
    payload = bytes.fromhex("62 F1 90") + b"XLRTE47MS0E123456"

    first = bytes([0x10, len(payload)]) + payload[:6]
    remaining = payload[6:]
    consecutive = [
        bytes([0x20 | sequence]) + remaining[offset : offset + 7]
        for sequence, offset in enumerate(range(0, len(remaining), 7), start=1)
    ]

    assert reassembler.feed(frame(0.0, can_id, first)) == []
    messages = []
    for index, data in enumerate(consecutive, start=1):
        messages.extend(reassembler.feed(frame(index * 0.01, can_id, data)))

    assert len(messages) == 1
    assert messages[0].payload == payload
    assert reassembler.dropped_messages == 0


def test_drops_conversation_on_wrong_sequence_number() -> None:
    reassembler = PassiveIsoTpReassembler()
    can_id = 0x18DAF930

    reassembler.feed(frame(0.0, can_id, bytes.fromhex("10 0A 62 F1 90 31 32 33")))
    assert reassembler.feed(frame(0.01, can_id, bytes.fromhex("22 34 35 36 37 38 39 30"))) == []
    assert reassembler.dropped_messages == 1
