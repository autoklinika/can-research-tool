from __future__ import annotations

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


def _require_canlib() -> Any:
    if canlib is None:
        raise KvaserUnavailableError(
            "Kvaser Python CANlib is not installed. Install CRT with the [kvaser] extra "
            "and install the Kvaser Windows driver."
        )
    return canlib


def _reset_acceptance_filters(channel: Any, api: Any) -> None:
    """Remove any receive filter before the handle is placed on bus.

    CANlib normally opens a fresh handle without an acceptance filter, but CRT
    makes this explicit so a stale driver/handle configuration cannot restrict
    the capture to one standard or extended identifier.
    """

    accept = getattr(channel, "canAccept", None)
    filter_flags = getattr(api, "AcceptFilterFlag", None)
    null_mask = getattr(filter_flags, "NULL_MASK", None)
    if callable(accept) and null_mask is not None:
        accept(0, null_mask)
        return

    setter = getattr(channel, "canSetAcceptanceFilter", None)
    if not callable(setter):
        return
    setter(code=0, mask=0, is_extended=False)
    setter(code=0, mask=0, is_extended=True)


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
    """

    def __init__(
        self,
        channel_number: int,
        bitrate: int,
        mode: KvaserReceiveMode = KvaserReceiveMode.BENCH,
    ) -> None:
        self.channel_number = channel_number
        self.bitrate = bitrate
        self.mode = KvaserReceiveMode(mode)
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
            _reset_acceptance_filters(channel, api)
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
