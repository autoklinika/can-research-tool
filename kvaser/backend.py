from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
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


class KvaserReceiveMode(StrEnum):
    """Electrical receive behaviour of the Kvaser controller.

    BENCH keeps the application read-only but allows the CAN controller to
    acknowledge correctly received frames. This is required when the observed
    ECU is otherwise alone on a bench bus.

    LISTEN_ONLY uses hardware silent mode and therefore does not acknowledge
    frames. Use it only when another active node on the bus provides ACK.
    """

    BENCH = "bench"
    LISTEN_ONLY = "listen-only"


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


DEFAULT_PREFETCH_LIMIT = 4_096


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
    """Read-only Kvaser capture channel with no application TX API.

    The default BENCH mode acknowledges valid CAN frames but still exposes no
    write/send operation. LISTEN_ONLY selects hardware silent mode and emits no
    ACK, which requires another active node on the observed network.

    CANlib keeps its own receive queue. CRT drains that queue into a bounded local
    prefetch buffer whenever the capture worker requests a frame. This prevents
    protocol decoding and disk serialization between individual reads from making
    the hardware/driver queue grow unnecessarily.
    """

    def __init__(
        self,
        channel_number: int,
        bitrate: int,
        mode: KvaserReceiveMode = KvaserReceiveMode.BENCH,
        *,
        prefetch_limit: int = DEFAULT_PREFETCH_LIMIT,
    ) -> None:
        if prefetch_limit <= 0:
            raise ValueError("prefetch_limit must be greater than zero")
        self.channel_number = channel_number
        self.bitrate = bitrate
        self.mode = KvaserReceiveMode(mode)
        self.prefetch_limit = int(prefetch_limit)
        self._channel: Any | None = None
        self._sequence = 0
        self._prefetched: deque[CanFrame] = deque()

    @property
    def is_open(self) -> bool:
        return self._channel is not None

    @property
    def prefetched_count(self) -> int:
        return len(self._prefetched)

    def open(self) -> None:
        if self._channel is not None:
            return

        api = _require_canlib()
        channel_data = api.ChannelData(self.channel_number)
        if self.mode is KvaserReceiveMode.LISTEN_ONLY and not bool(
            channel_data.channel_cap & api.ChannelCap.SILENT_MODE
        ):
            raise SilentModeRequiredError(
                f"Kvaser channel {self.channel_number} does not report SILENT_MODE capability"
            )

        bitrate_name = _BITRATES.get(self.bitrate)
        if bitrate_name is None:
            raise ValueError(f"Unsupported predefined CAN bitrate: {self.bitrate}")
        bitrate_value = getattr(api.Bitrate, bitrate_name)

        channel = api.openChannel(self.channel_number, bitrate=bitrate_value)
        try:
            channel.iocontrol.local_txecho = False
            driver = (
                api.Driver.SILENT
                if self.mode is KvaserReceiveMode.LISTEN_ONLY
                else api.Driver.NORMAL
            )
            channel.setBusOutputControl(driver)
            channel.busOn()
            channel.iocontrol.flush_rx_buffer()
        except Exception:
            channel.close()
            raise

        self._channel = channel
        self._sequence = 0
        self._prefetched.clear()

    def read(self, timeout_ms: int = 100) -> CanFrame | None:
        if self._channel is None:
            raise RuntimeError("Kvaser channel is not open")
        if timeout_ms < 0:
            raise ValueError("timeout_ms cannot be negative")

        if self._prefetched:
            return self._prefetched.popleft()

        first = self._read_one(timeout_ms)
        if first is None:
            return None
        self._prefetched.append(first)

        # After the first blocking read, drain every frame that CANlib already has
        # queued. Subsequent calls are non-blocking and bounded, so the capture
        # worker regains control even on a saturated bus.
        for _ in range(self.prefetch_limit - 1):
            frame = self._read_one(0)
            if frame is None:
                break
            self._prefetched.append(frame)

        return self._prefetched.popleft()

    def _read_one(self, timeout_ms: int) -> CanFrame | None:
        channel = self._channel
        if channel is None:
            raise RuntimeError("Kvaser channel is not open")

        api = _require_canlib()
        try:
            frame = channel.read(timeout=timeout_ms)
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
        self._prefetched.clear()
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
