from __future__ import annotations

from dataclasses import dataclass

from .models import CanFrame, IsoTpMessage


@dataclass(slots=True)
class _RxState:
    expected_length: int
    payload: bytearray
    next_sequence_number: int
    started_at_s: float


class PassiveIsoTpReassembler:
    """Reassembles ISO-TP messages without transmitting flow-control frames."""

    def __init__(self) -> None:
        self._states: dict[int, _RxState] = {}
        self.dropped_messages = 0

    def reset(self) -> None:
        self._states.clear()
        self.dropped_messages = 0

    def feed(self, frame: CanFrame) -> list[IsoTpMessage]:
        if not frame.data:
            return []

        pci_type = frame.data[0] >> 4
        if pci_type == 0x0:
            return self._handle_single_frame(frame)
        if pci_type == 0x1:
            self._handle_first_frame(frame)
            return []
        if pci_type == 0x2:
            message = self._handle_consecutive_frame(frame)
            return [message] if message is not None else []
        if pci_type == 0x3:
            return []
        return []

    def _handle_single_frame(self, frame: CanFrame) -> list[IsoTpMessage]:
        payload_length = frame.data[0] & 0x0F
        if payload_length == 0 or payload_length > len(frame.data) - 1:
            self.dropped_messages += 1
            return []

        payload = frame.data[1 : 1 + payload_length]
        self._states.pop(frame.arbitration_id, None)
        return [
            IsoTpMessage(
                arbitration_id=frame.arbitration_id,
                payload=payload,
                started_at_s=frame.timestamp_s,
                completed_at_s=frame.timestamp_s,
            )
        ]

    def _handle_first_frame(self, frame: CanFrame) -> None:
        if len(frame.data) < 2:
            self.dropped_messages += 1
            return

        expected_length = ((frame.data[0] & 0x0F) << 8) | frame.data[1]
        if expected_length <= 7:
            self.dropped_messages += 1
            return

        self._states[frame.arbitration_id] = _RxState(
            expected_length=expected_length,
            payload=bytearray(frame.data[2:]),
            next_sequence_number=1,
            started_at_s=frame.timestamp_s,
        )

    def _handle_consecutive_frame(self, frame: CanFrame) -> IsoTpMessage | None:
        state = self._states.get(frame.arbitration_id)
        if state is None:
            self.dropped_messages += 1
            return None

        sequence_number = frame.data[0] & 0x0F
        if sequence_number != state.next_sequence_number:
            self._states.pop(frame.arbitration_id, None)
            self.dropped_messages += 1
            return None

        state.payload.extend(frame.data[1:])
        state.next_sequence_number = (state.next_sequence_number + 1) & 0x0F

        if len(state.payload) < state.expected_length:
            return None

        payload = bytes(state.payload[: state.expected_length])
        self._states.pop(frame.arbitration_id, None)
        return IsoTpMessage(
            arbitration_id=frame.arbitration_id,
            payload=payload,
            started_at_s=state.started_at_s,
            completed_at_s=frame.timestamp_s,
        )
