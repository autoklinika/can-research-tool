from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from queue import Empty, Queue
from threading import Event, Thread
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


class KvaserReceiveError(RuntimeError):
    pass


class KvaserReceiveMode(StrEnum):
    """Electrical receive behaviour of the Kvaser controller.

    BENCH keeps the application read-only but allows the CAN controller to
    acknowledge correctly received frames. This is required when the observed
    ECU is otherwise alone on a bench bus.

    LISTEN_ONLY uses hardware silent mode and therefore does not acknowledge
    frames. Use it only when another active node on the observed network
    provides ACK.
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

DRIVER_READ_TIMEOUT_MS = 1


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
    """Read-only Kvaser channel with a dedicated CANlib receive thread.

    The CANlib channel is owned by a lightweight reader thread after ``open``.
    That thread performs only ``read(timeout=1)`` and converts the result into a
    hardware-neutral ``CanFrame`` before placing it in an in-process queue.
    Disk writes, transport reassembly, protocol decoding and GUI publication are
    therefore unable to delay reads from the CANlib driver queue.

    The implementation intentionally mirrors the proven receive path used by the
    standalone Kvaser monitor: explicit ``setBusParams`` before ``busOn`` and a
    continuously running reader thread.
    """

    def __init__(
        self,
        channel_number: int,
        bitrate: int,
        mode: KvaserReceiveMode = KvaserReceiveMode.BENCH,
        *,
        driver_read_timeout_ms: int = DRIVER_READ_TIMEOUT_MS,
    ) -> None:
        if driver_read_timeout_ms <= 0:
            raise ValueError("driver_read_timeout_ms must be greater than zero")
        self.channel_number = channel_number
        self.bitrate = bitrate
        self.mode = KvaserReceiveMode(mode)
        self.driver_read_timeout_ms = int(driver_read_timeout_ms)
        self._channel: Any | None = None
        self._sequence = 0
        self._frames: Queue[CanFrame] = Queue()
        self._reader_stop = Event()
        self._reader_thread: Thread | None = None
        self._reader_error: BaseException | None = None

    @property
    def is_open(self) -> bool:
        return self._channel is not None

    @property
    def prefetched_count(self) -> int:
        """Number of frames already removed from CANlib and awaiting processing."""

        return self._frames.qsize()

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

        # Match the known-good standalone monitor exactly: open first, then select
        # driver mode and nominal bus parameters before putting the channel bus-on.
        channel = api.openChannel(self.channel_number)
        try:
            channel.iocontrol.local_txecho = False
            driver = (
                api.Driver.SILENT
                if self.mode is KvaserReceiveMode.LISTEN_ONLY
                else api.Driver.NORMAL
            )
            channel.setBusOutputControl(driver)
            channel.setBusParams(bitrate_value)
            channel.busOn()
        except Exception:
            channel.close()
            raise

        self._channel = channel
        self._sequence = 0
        self._frames = Queue()
        self._reader_error = None
        self._reader_stop = Event()
        self._reader_thread = Thread(
            target=self._receive_loop,
            name=f"crt-kvaser-rx-{self.channel_number}",
            daemon=True,
        )
        self._reader_thread.start()

    def read(self, timeout_ms: int = 100) -> CanFrame | None:
        """Return a frame already drained from CANlib by the reader thread."""

        if self._channel is None:
            raise RuntimeError("Kvaser channel is not open")
        if timeout_ms < 0:
            raise ValueError("timeout_ms cannot be negative")

        try:
            if timeout_ms == 0:
                return self._frames.get_nowait()
            return self._frames.get(timeout=timeout_ms / 1000.0)
        except Empty:
            if self._reader_error is not None:
                raise KvaserReceiveError(
                    f"Kvaser receive thread failed: {self._reader_error}"
                ) from self._reader_error
            return None

    def _receive_loop(self) -> None:
        channel = self._channel
        if channel is None:
            return
        api = _require_canlib()

        while not self._reader_stop.is_set():
            try:
                frame = channel.read(timeout=self.driver_read_timeout_ms)
            except api.CanNoMsg:
                continue
            except Exception as exc:
                if not self._reader_stop.is_set():
                    self._reader_error = exc
                break

            flags = frame.flags
            captured = CanFrame(
                sequence=self._sequence,
                timestamp_ns=perf_counter_ns(),
                arbitration_id=int(frame.id),
                data=bytes(frame.data[: frame.dlc]),
                channel=self.channel_number,
                is_extended_id=bool(flags & api.MessageFlag.EXT),
                is_remote_frame=bool(flags & api.MessageFlag.RTR),
                is_error_frame=bool(flags & api.MessageFlag.ERROR_FRAME),
                source_timestamp=int(frame.timestamp),
                source_flags=int(flags),
            )
            self._sequence += 1
            self._frames.put(captured)

    def close(self) -> None:
        channel = self._channel
        if channel is None:
            return

        self._reader_stop.set()
        reader = self._reader_thread
        if reader is not None:
            reader.join(timeout=max(1.0, self.driver_read_timeout_ms / 1000.0 * 10))
        self._reader_thread = None
        self._channel = None

        try:
            channel.busOff()
        finally:
            channel.close()

        while True:
            try:
                self._frames.get_nowait()
            except Empty:
                break

    def __enter__(self) -> "KvaserPassiveChannel":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
