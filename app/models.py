from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class CanFrame:
    """Hardware-neutral CAN frame captured by CRT."""

    sequence: int
    timestamp_ns: int
    arbitration_id: int
    data: bytes
    channel: int = 0
    is_extended_id: bool = False
    is_remote_frame: bool = False
    is_error_frame: bool = False
    source_timestamp: int | None = None
    source_flags: int = 0

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence cannot be negative")
        if self.timestamp_ns < 0:
            raise ValueError("timestamp_ns cannot be negative")
        maximum_id = 0x1FFFFFFF if self.is_extended_id else 0x7FF
        if not 0 <= self.arbitration_id <= maximum_id:
            raise ValueError("arbitration_id is outside the selected CAN ID range")
        if len(self.data) > 64:
            raise ValueError("CAN payload cannot exceed 64 bytes")

    @property
    def dlc(self) -> int:
        return len(self.data)

    @property
    def data_hex(self) -> str:
        return " ".join(f"{byte:02X}" for byte in self.data)


@dataclass(slots=True)
class CaptureSession:
    """One passive CAN observation with source and hardware metadata."""

    name: str
    source: str
    started_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    bitrate: int | None = None
    channel: int | None = None
    adapter: str = ""
    notes: str = ""
    frames: list[CanFrame] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def append(self, frame: CanFrame) -> None:
        if self.frames and frame.sequence <= self.frames[-1].sequence:
            raise ValueError("frame sequence must be strictly increasing")
        self.frames.append(frame)
