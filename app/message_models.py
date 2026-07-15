from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TransportKind(StrEnum):
    RAW = "raw"
    J1939_BAM = "j1939-bam"
    J1939_RTS_CTS = "j1939-rts-cts"
    ISOTP = "isotp"


class ProtocolKind(StrEnum):
    UNKNOWN = "unknown"
    J1939 = "j1939"
    UDS = "uds"
    DBC = "dbc"
    PROPRIETARY = "proprietary"


@dataclass(frozen=True, slots=True)
class TransportMessage:
    """Hardware-neutral logical message reconstructed from one or more CAN frames."""

    sequence: int
    first_timestamp_ns: int
    last_timestamp_ns: int
    transport: TransportKind
    payload: bytes
    frame_sequences: tuple[int, ...]
    arbitration_id: int | None = None
    is_extended_id: bool = False
    source_address: int | None = None
    destination_address: int | None = None
    pgn: int | None = None
    complete: bool = True
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence cannot be negative")
        if self.first_timestamp_ns < 0 or self.last_timestamp_ns < 0:
            raise ValueError("timestamps cannot be negative")
        if self.last_timestamp_ns < self.first_timestamp_ns:
            raise ValueError("last_timestamp_ns cannot precede first_timestamp_ns")
        if not self.frame_sequences:
            raise ValueError("frame_sequences cannot be empty")

    @property
    def payload_hex(self) -> str:
        return " ".join(f"{byte:02X}" for byte in self.payload)

    @property
    def frame_count(self) -> int:
        return len(self.frame_sequences)


@dataclass(frozen=True, slots=True)
class DecodedMessage:
    """Protocol interpretation layered on top of a transport message."""

    message: TransportMessage
    protocol: ProtocolKind
    name: str
    fields: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
