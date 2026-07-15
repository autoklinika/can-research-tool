from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .j1939 import decode_j1939_identifier
from .message_models import TransportKind, TransportMessage
from .models import CanFrame
from .transport import IsoTpReassembler, J1939TpReassembler, TransportReassembler


class StreamingTransportPipeline:
    """Incremental counterpart of ``TransportPipeline`` for live capture.

    Reassembler state remains alive between calls to ``feed``. Nothing is
    flushed until ``flush`` is called when capture stops.
    """

    def __init__(self, reassemblers: Iterable[TransportReassembler] | None = None) -> None:
        self._reassemblers = list(
            reassemblers
            if reassemblers is not None
            else (J1939TpReassembler(), IsoTpReassembler())
        )
        self._next_sequence = 0

    def feed(self, frame: CanFrame) -> list[TransportMessage]:
        for reassembler in self._reassemblers:
            if not reassembler.accepts(frame):
                continue
            return self._assign_sequences(reassembler.feed(frame))
        return [self._assign_sequence(self._raw_message(frame))]

    def feed_many(self, frames: Iterable[CanFrame]) -> list[TransportMessage]:
        messages: list[TransportMessage] = []
        for frame in frames:
            messages.extend(self.feed(frame))
        return messages

    def flush(self) -> list[TransportMessage]:
        messages: list[TransportMessage] = []
        for reassembler in self._reassemblers:
            messages.extend(self._assign_sequences(reassembler.flush()))
        return sorted(messages, key=lambda item: (item.first_timestamp_ns, item.sequence))

    def _assign_sequences(
        self,
        messages: Iterable[TransportMessage],
    ) -> list[TransportMessage]:
        return [self._assign_sequence(message) for message in messages]

    def _assign_sequence(self, message: TransportMessage) -> TransportMessage:
        assigned = replace(message, sequence=self._next_sequence)
        self._next_sequence += 1
        return assigned

    @staticmethod
    def _raw_message(frame: CanFrame) -> TransportMessage:
        source = destination = pgn = None
        metadata: dict[str, object] = {}
        if frame.is_extended_id:
            identifier = decode_j1939_identifier(frame.arbitration_id)
            source = identifier.source_address
            destination = identifier.destination_address
            pgn = identifier.pgn
            metadata["j1939_identifier_candidate"] = {
                "priority": identifier.priority,
                "pdu_format": identifier.pdu_format,
                "pdu_specific": identifier.pdu_specific,
                "pgn": identifier.pgn,
            }

        return TransportMessage(
            sequence=0,
            first_timestamp_ns=frame.timestamp_ns,
            last_timestamp_ns=frame.timestamp_ns,
            transport=TransportKind.RAW,
            payload=bytes(frame.data),
            frame_sequences=(frame.sequence,),
            arbitration_id=frame.arbitration_id,
            is_extended_id=frame.is_extended_id,
            source_address=source,
            destination_address=destination,
            pgn=pgn,
            complete=not frame.is_error_frame,
            error="CAN error frame" if frame.is_error_frame else "",
            metadata=metadata,
        )
