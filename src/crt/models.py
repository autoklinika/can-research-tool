from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FrameDirection(StrEnum):
    RX = "rx"
    TX = "tx"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CanFrame:
    timestamp_s: float
    arbitration_id: int
    data: bytes
    channel: str = ""
    direction: FrameDirection = FrameDirection.UNKNOWN
    is_extended_id: bool | None = None

    def __post_init__(self) -> None:
        if self.timestamp_s < 0:
            raise ValueError("timestamp_s cannot be negative")
        if not 0 <= self.arbitration_id <= 0x1FFFFFFF:
            raise ValueError("arbitration_id is outside the CAN 29-bit range")
        if len(self.data) > 64:
            raise ValueError("CAN payload cannot exceed 64 bytes")
        if self.is_extended_id is None:
            object.__setattr__(self, "is_extended_id", self.arbitration_id > 0x7FF)

    @property
    def data_hex(self) -> str:
        return " ".join(f"{byte:02X}" for byte in self.data)


@dataclass(frozen=True, slots=True)
class IsoTpMessage:
    arbitration_id: int
    payload: bytes
    started_at_s: float
    completed_at_s: float

    @property
    def payload_hex(self) -> str:
        return " ".join(f"{byte:02X}" for byte in self.payload)


@dataclass(frozen=True, slots=True)
class DecodedEvent:
    timestamp_s: float
    arbitration_id: int
    direction: str
    protocol: str
    name: str
    details: str
    payload: bytes
    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def payload_hex(self) -> str:
        return " ".join(f"{byte:02X}" for byte in self.payload)
