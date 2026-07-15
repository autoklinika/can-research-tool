from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import ceil
from typing import Iterable, Protocol

from .j1939 import decode_j1939_identifier
from .message_models import TransportKind, TransportMessage
from .models import CanFrame


class TransportReassembler(Protocol):
    def accepts(self, frame: CanFrame) -> bool: ...

    def feed(self, frame: CanFrame) -> list[TransportMessage]: ...

    def flush(self) -> list[TransportMessage]: ...


@dataclass(slots=True)
class _J1939Session:
    transport: TransportKind
    total_size: int
    packet_count: int
    pgn: int
    source: int
    destination: int
    first_timestamp_ns: int
    last_timestamp_ns: int
    frame_sequences: list[int] = field(default_factory=list)
    chunks: dict[int, bytes] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class J1939TpReassembler:
    """Reassemble J1939 TP BAM and RTS/CTS payloads.

    The raw capture remains untouched. This layer only creates an additional
    logical-message view.
    """

    TP_CM_PF = 0xEC
    TP_DT_PF = 0xEB
    CM_RTS = 0x10
    CM_BAM = 0x20
    CM_ABORT = 0xFF

    def __init__(self) -> None:
        self._sessions: dict[tuple[int, int], _J1939Session] = {}

    def accepts(self, frame: CanFrame) -> bool:
        if not frame.is_extended_id or not frame.data:
            return False
        identifier = decode_j1939_identifier(frame.arbitration_id)
        return identifier.pdu_format in (self.TP_CM_PF, self.TP_DT_PF)

    def feed(self, frame: CanFrame) -> list[TransportMessage]:
        identifier = decode_j1939_identifier(frame.arbitration_id)
        if identifier.pdu_format == self.TP_CM_PF:
            return self._feed_cm(frame, identifier.source_address, identifier.pdu_specific)
        return self._feed_dt(frame, identifier.source_address, identifier.pdu_specific)

    def flush(self) -> list[TransportMessage]:
        messages = [
            self._build_message(session, complete=False, error="capture ended before TP completion")
            for session in self._sessions.values()
        ]
        self._sessions.clear()
        return messages

    def _feed_cm(self, frame: CanFrame, source: int, destination: int) -> list[TransportMessage]:
        control = frame.data[0]
        if control in (self.CM_BAM, self.CM_RTS):
            return self._start_session(frame, source, destination, control)

        if control == self.CM_ABORT:
            key = (source, destination)
            reverse_key = (destination, source)
            session = self._sessions.pop(key, None) or self._sessions.pop(reverse_key, None)
            if session is None:
                return [self._orphan_control(frame, source, destination, "orphan TP abort")]
            session.last_timestamp_ns = frame.timestamp_ns
            session.frame_sequences.append(frame.sequence)
            return [self._build_message(session, complete=False, error="J1939 TP aborted")]

        # CTS and EOM_ACK belong to transport mechanics and do not create
        # standalone application messages.
        return []

    def _start_session(
        self,
        frame: CanFrame,
        source: int,
        destination: int,
        control: int,
    ) -> list[TransportMessage]:
        if len(frame.data) < 8:
            return [self._orphan_control(frame, source, destination, "truncated TP.CM frame")]

        total_size = int.from_bytes(frame.data[1:3], "little")
        packet_count = frame.data[3]
        pgn = int.from_bytes(frame.data[5:8], "little")
        transport = (
            TransportKind.J1939_BAM if control == self.CM_BAM else TransportKind.J1939_RTS_CTS
        )
        key = (source, destination)
        messages: list[TransportMessage] = []

        previous = self._sessions.pop(key, None)
        if previous is not None:
            messages.append(
                self._build_message(
                    previous,
                    complete=False,
                    error="new TP session replaced an unfinished session",
                )
            )

        session = _J1939Session(
            transport=transport,
            total_size=total_size,
            packet_count=packet_count,
            pgn=pgn,
            source=source,
            destination=destination,
            first_timestamp_ns=frame.timestamp_ns,
            last_timestamp_ns=frame.timestamp_ns,
            frame_sequences=[frame.sequence],
        )
        expected_packets = ceil(total_size / 7) if total_size else 0
        if total_size <= 0:
            session.errors.append("invalid TP payload length")
        if packet_count <= 0:
            session.errors.append("invalid TP packet count")
        if expected_packets and packet_count != expected_packets:
            session.errors.append(
                f"packet count mismatch: header={packet_count}, expected={expected_packets}"
            )
        self._sessions[key] = session
        return messages

    def _feed_dt(self, frame: CanFrame, source: int, destination: int) -> list[TransportMessage]:
        if len(frame.data) < 2:
            return [self._orphan_control(frame, source, destination, "truncated TP.DT frame")]

        key = (source, destination)
        session = self._sessions.get(key)
        if session is None:
            return [
                TransportMessage(
                    sequence=0,
                    first_timestamp_ns=frame.timestamp_ns,
                    last_timestamp_ns=frame.timestamp_ns,
                    transport=TransportKind.J1939_BAM,
                    payload=bytes(frame.data[1:]),
                    frame_sequences=(frame.sequence,),
                    arbitration_id=frame.arbitration_id,
                    is_extended_id=True,
                    source_address=source,
                    destination_address=destination,
                    complete=False,
                    error="orphan TP.DT frame",
                    metadata={"packet_number": frame.data[0]},
                )
            ]

        packet_number = frame.data[0]
        session.last_timestamp_ns = frame.timestamp_ns
        session.frame_sequences.append(frame.sequence)

        if not 1 <= packet_number <= session.packet_count:
            session.errors.append(f"invalid TP.DT packet number {packet_number}")
        elif packet_number in session.chunks:
            session.errors.append(f"duplicate TP.DT packet {packet_number}")
        else:
            session.chunks[packet_number] = bytes(frame.data[1:])

        if all(number in session.chunks for number in range(1, session.packet_count + 1)):
            self._sessions.pop(key, None)
            payload = b"".join(
                session.chunks[number] for number in range(1, session.packet_count + 1)
            )
            complete = len(payload) >= session.total_size and not any(
                error.startswith("invalid") for error in session.errors
            )
            return [
                self._build_message(
                    session,
                    complete=complete,
                    error="; ".join(session.errors),
                )
            ]
        return []

    @staticmethod
    def _build_message(
        session: _J1939Session,
        *,
        complete: bool,
        error: str = "",
    ) -> TransportMessage:
        payload = b"".join(
            session.chunks[number] for number in sorted(session.chunks)
        )[: session.total_size]
        errors = [item for item in session.errors if item]
        if error:
            errors.append(error)
        return TransportMessage(
            sequence=0,
            first_timestamp_ns=session.first_timestamp_ns,
            last_timestamp_ns=session.last_timestamp_ns,
            transport=session.transport,
            payload=payload,
            frame_sequences=tuple(session.frame_sequences),
            is_extended_id=True,
            source_address=session.source,
            destination_address=session.destination,
            pgn=session.pgn,
            complete=complete,
            error="; ".join(dict.fromkeys(errors)),
            metadata={
                "declared_payload_length": session.total_size,
                "declared_packet_count": session.packet_count,
                "received_packet_count": len(session.chunks),
            },
        )

    @staticmethod
    def _orphan_control(
        frame: CanFrame,
        source: int,
        destination: int,
        error: str,
    ) -> TransportMessage:
        return TransportMessage(
            sequence=0,
            first_timestamp_ns=frame.timestamp_ns,
            last_timestamp_ns=frame.timestamp_ns,
            transport=TransportKind.J1939_BAM,
            payload=bytes(frame.data),
            frame_sequences=(frame.sequence,),
            arbitration_id=frame.arbitration_id,
            is_extended_id=True,
            source_address=source,
            destination_address=destination,
            complete=False,
            error=error,
        )


@dataclass(slots=True)
class _IsoTpSession:
    total_size: int
    arbitration_id: int
    is_extended_id: bool
    source: int | None
    destination: int | None
    first_timestamp_ns: int
    last_timestamp_ns: int
    frame_sequences: list[int]
    payload: bytearray
    expected_sequence_number: int = 1


class IsoTpReassembler:
    """Conservative ISO-TP detector for common UDS addressing schemes.

    Automatic detection is intentionally limited to 29-bit normal-fixed IDs
    (PF 0xDA/0xDB) and the standard 0x7DF/0x7E0-0x7EF diagnostic range. Other
    proprietary frames remain RAW unless a future user rule explicitly selects
    ISO-TP for them.
    """

    def __init__(self) -> None:
        self._sessions: dict[tuple[int, bool], _IsoTpSession] = {}

    def accepts(self, frame: CanFrame) -> bool:
        if not frame.data:
            return False
        pci_type = frame.data[0] >> 4
        if pci_type not in (0, 1, 2, 3):
            return False
        if frame.is_extended_id:
            pdu_format = (frame.arbitration_id >> 16) & 0xFF
            return pdu_format in (0xDA, 0xDB)
        return frame.arbitration_id == 0x7DF or 0x7E0 <= frame.arbitration_id <= 0x7EF

    def feed(self, frame: CanFrame) -> list[TransportMessage]:
        pci_type = frame.data[0] >> 4
        if pci_type == 0:
            return [self._single_frame(frame)]
        if pci_type == 1:
            return self._first_frame(frame)
        if pci_type == 2:
            return self._consecutive_frame(frame)
        return []

    def flush(self) -> list[TransportMessage]:
        messages = [
            self._build_incomplete(session, "capture ended before ISO-TP completion")
            for session in self._sessions.values()
        ]
        self._sessions.clear()
        return messages

    def _single_frame(self, frame: CanFrame) -> TransportMessage:
        nibble_length = frame.data[0] & 0x0F
        if nibble_length:
            payload_length = nibble_length
            header_size = 1
        elif len(frame.data) >= 2:
            payload_length = frame.data[1]
            header_size = 2
        else:
            payload_length = 0
            header_size = 1

        available = max(0, len(frame.data) - header_size)
        complete = payload_length <= available
        payload = bytes(frame.data[header_size : header_size + payload_length])
        source, destination, addressing = self._addresses(frame)
        return TransportMessage(
            sequence=0,
            first_timestamp_ns=frame.timestamp_ns,
            last_timestamp_ns=frame.timestamp_ns,
            transport=TransportKind.ISOTP,
            payload=payload,
            frame_sequences=(frame.sequence,),
            arbitration_id=frame.arbitration_id,
            is_extended_id=frame.is_extended_id,
            source_address=source,
            destination_address=destination,
            complete=complete,
            error="" if complete else "ISO-TP single frame shorter than declared length",
            metadata={
                "addressing": addressing,
                "declared_payload_length": payload_length,
            },
        )

    def _first_frame(self, frame: CanFrame) -> list[TransportMessage]:
        if len(frame.data) < 2:
            return [self._orphan(frame, "truncated ISO-TP first frame")]

        total_size = ((frame.data[0] & 0x0F) << 8) | frame.data[1]
        header_size = 2
        if total_size == 0:
            if len(frame.data) < 6:
                return [self._orphan(frame, "truncated ISO-TP extended-length first frame")]
            total_size = int.from_bytes(frame.data[2:6], "big")
            header_size = 6

        key = (frame.arbitration_id, frame.is_extended_id)
        messages: list[TransportMessage] = []
        previous = self._sessions.pop(key, None)
        if previous is not None:
            messages.append(
                self._build_incomplete(
                    previous,
                    "new ISO-TP first frame replaced an unfinished session",
                )
            )

        source, destination, _ = self._addresses(frame)
        session = _IsoTpSession(
            total_size=total_size,
            arbitration_id=frame.arbitration_id,
            is_extended_id=frame.is_extended_id,
            source=source,
            destination=destination,
            first_timestamp_ns=frame.timestamp_ns,
            last_timestamp_ns=frame.timestamp_ns,
            frame_sequences=[frame.sequence],
            payload=bytearray(frame.data[header_size:]),
        )
        self._sessions[key] = session

        if len(session.payload) >= total_size:
            self._sessions.pop(key, None)
            messages.append(self._build_complete(session))
        return messages

    def _consecutive_frame(self, frame: CanFrame) -> list[TransportMessage]:
        key = (frame.arbitration_id, frame.is_extended_id)
        session = self._sessions.get(key)
        if session is None:
            return [self._orphan(frame, "orphan ISO-TP consecutive frame")]

        sequence_number = frame.data[0] & 0x0F
        if sequence_number != session.expected_sequence_number:
            self._sessions.pop(key, None)
            session.last_timestamp_ns = frame.timestamp_ns
            session.frame_sequences.append(frame.sequence)
            return [
                self._build_incomplete(
                    session,
                    (
                        "ISO-TP sequence mismatch: "
                        f"expected {session.expected_sequence_number}, got {sequence_number}"
                    ),
                )
            ]

        session.payload.extend(frame.data[1:])
        session.last_timestamp_ns = frame.timestamp_ns
        session.frame_sequences.append(frame.sequence)
        session.expected_sequence_number = (session.expected_sequence_number + 1) & 0x0F

        if len(session.payload) >= session.total_size:
            self._sessions.pop(key, None)
            return [self._build_complete(session)]
        return []

    def _build_complete(self, session: _IsoTpSession) -> TransportMessage:
        _, _, addressing = self._addresses_from_values(
            session.arbitration_id,
            session.is_extended_id,
        )
        return TransportMessage(
            sequence=0,
            first_timestamp_ns=session.first_timestamp_ns,
            last_timestamp_ns=session.last_timestamp_ns,
            transport=TransportKind.ISOTP,
            payload=bytes(session.payload[: session.total_size]),
            frame_sequences=tuple(session.frame_sequences),
            arbitration_id=session.arbitration_id,
            is_extended_id=session.is_extended_id,
            source_address=session.source,
            destination_address=session.destination,
            complete=True,
            metadata={
                "addressing": addressing,
                "declared_payload_length": session.total_size,
            },
        )

    def _build_incomplete(self, session: _IsoTpSession, error: str) -> TransportMessage:
        _, _, addressing = self._addresses_from_values(
            session.arbitration_id,
            session.is_extended_id,
        )
        return TransportMessage(
            sequence=0,
            first_timestamp_ns=session.first_timestamp_ns,
            last_timestamp_ns=session.last_timestamp_ns,
            transport=TransportKind.ISOTP,
            payload=bytes(session.payload[: session.total_size]),
            frame_sequences=tuple(session.frame_sequences),
            arbitration_id=session.arbitration_id,
            is_extended_id=session.is_extended_id,
            source_address=session.source,
            destination_address=session.destination,
            complete=False,
            error=error,
            metadata={
                "addressing": addressing,
                "declared_payload_length": session.total_size,
                "received_payload_length": min(len(session.payload), session.total_size),
            },
        )

    def _orphan(self, frame: CanFrame, error: str) -> TransportMessage:
        source, destination, addressing = self._addresses(frame)
        return TransportMessage(
            sequence=0,
            first_timestamp_ns=frame.timestamp_ns,
            last_timestamp_ns=frame.timestamp_ns,
            transport=TransportKind.ISOTP,
            payload=bytes(frame.data),
            frame_sequences=(frame.sequence,),
            arbitration_id=frame.arbitration_id,
            is_extended_id=frame.is_extended_id,
            source_address=source,
            destination_address=destination,
            complete=False,
            error=error,
            metadata={"addressing": addressing},
        )

    @classmethod
    def _addresses(cls, frame: CanFrame) -> tuple[int | None, int | None, str]:
        return cls._addresses_from_values(frame.arbitration_id, frame.is_extended_id)

    @staticmethod
    def _addresses_from_values(
        arbitration_id: int,
        is_extended_id: bool,
    ) -> tuple[int | None, int | None, str]:
        if is_extended_id:
            return arbitration_id & 0xFF, (arbitration_id >> 8) & 0xFF, "normal-fixed-29bit"
        return None, None, "normal-11bit"


class TransportPipeline:
    """Run independent transport plugins with a RAW fallback."""

    def __init__(self, reassemblers: Iterable[TransportReassembler] | None = None) -> None:
        self._reassemblers = list(
            reassemblers
            if reassemblers is not None
            else (J1939TpReassembler(), IsoTpReassembler())
        )
        self._next_sequence = 0

    def process(self, frames: Iterable[CanFrame]) -> list[TransportMessage]:
        messages: list[TransportMessage] = []
        for frame in frames:
            handled = False
            for reassembler in self._reassemblers:
                if not reassembler.accepts(frame):
                    continue
                handled = True
                messages.extend(self._assign_sequences(reassembler.feed(frame)))
                break
            if not handled:
                messages.append(self._assign_sequence(self._raw_message(frame)))

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
