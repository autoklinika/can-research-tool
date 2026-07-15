from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any

from app.models import CanFrame

try:
    from canlib import canlib
except ImportError:  # pragma: no cover - exercised only without optional dependency
    canlib = None  # type: ignore[assignment]


class KvaserUnavailableError(RuntimeError):
    pass


class SilentModeRequiredError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class KvaserChannelInfo:
    number: int
    name: str
    serial_number: str
    product_number: str
    supports_silent_mode: bool


_BITRATES: dict[int, str] = {
    10_000: "BITRATE_10K",
    50_000: "BITRATE_50K",
    62_000: "BITRATE_62K",
    83_000: "BITRATE_83K",
    100_000: "BITRATE_100K",
    125_000: "BITRATE_125K",
    250_000: "BITRATE_250K",
    500_000: "BITRATE_500K",
    1_000_000: "BITRATE_1M",
}


def _require_canlib() -> Any:
    if canlib is None:
        raise KvaserUnavailableError(
            "Kvaser Python CANlib is not installed. Install CRT with the [kvaser] extra "
            "and install the Kvaser Windows driver."
        )
    return canlib


def list_channels() -> list[KvaserChannelInfo]:
    api = _require_canlib()
    channels: list[KvaserChannelInfo] = []

    for number in range(api.getNumberOfChannels()):
        data = api.ChannelData(number)
        capabilities = data.channel_cap
        channels.append(
            KvaserChannelInfo(
                number=number,
                name=str(data.channel_name),
                serial_number=str(data.card_serial_no),
                product_number=str(data.card_upc_no),
                supports_silent_mode=bool(capabilities & api.ChannelCap.SILENT_MODE),
            )
        )

    return channels


class KvaserPassiveChannel:
    """Read-only Kvaser channel that refuses to run without hardware silent mode.

    This class intentionally exposes no write/send operation.
    """

    def __init__(self, channel_number: int, bitrate: int) -> None:
        self.channel_number = channel_number
        self.bitrate = bitrate
        self._channel: Any | None = None
        self._sequence = 0

    @property
    def is_open(self) -> bool:
        return self._channel is not None

    def open(self) -> None:
        if self._channel is not None:
            return

        api = _require_canlib()
        channel_data = api.ChannelData(self.channel_number)
        if not bool(channel_data.channel_cap & api.ChannelCap.SILENT_MODE):
            raise SilentModeRequiredError(
                f"Kvaser channel {self.channel_number} does not report SILENT_MODE capability"
            )

        bitrate_name = _BITRATES.get(self.bitrate)
        if bitrate_name is None:
            raise ValueError(f"Unsupported predefined CAN bitrate: {self.bitrate}")
        bitrate_value = getattr(api.Bitrate, bitrate_name)

        channel = api.openChannel(self.channel_number, bitrate=bitrate_value)
        try:
            channel.setBusOutputControl(api.Driver.SILENT)
            channel.busOn()
        except Exception:
            channel.close()
            raise

        self._channel = channel
        self._sequence = 0

    def read(self, timeout_ms: int = 100) -> CanFrame | None:
        if self._channel is None:
            raise RuntimeError("Kvaser channel is not open")
        if timeout_ms < 0:
            raise ValueError("timeout_ms cannot be negative")

        api = _require_canlib()
        try:
            frame = self._channel.read(timeout=timeout_ms)
        except api.CanNoMsg:
            return None

        flags = frame.flags
        captured = CanFrame(
            sequence=self._sequence,
            timestamp_ns=perf_counter_ns(),
            arbitration_id=int(frame.id),
            data=bytes(frame.data),
            channel=self.channel_number,
            is_extended_id=bool(flags & api.MessageFlag.EXT),
            is_remote_frame=bool(flags & api.MessageFlag.RTR),
            is_error_frame=bool(flags & api.MessageFlag.ERROR_FRAME),
            source_timestamp=int(frame.timestamp),
            source_flags=int(flags),
        )
        self._sequence += 1
        return captured

    def close(self) -> None:
        channel = self._channel
        self._channel = None
        if channel is None:
            return
        try:
            channel.busOff()
        finally:
            channel.close()

    def __enter__(self) -> "KvaserPassiveChannel":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
