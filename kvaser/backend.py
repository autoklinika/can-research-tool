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
READER_START_TIMEOUT_S = 5.0
READER_STOP_TIMEOUT_S = 2.0

#: Requested CANlib timer resolution in microseconds (CANlib default is 1000 µs).
HARDWARE_TIMER_SCALE_US = 1
#: CANlib reports frame timestamps as an unsigned 32-bit counter on most drivers.
_TIMER_WRAP = 1 << 32

TIMESTAMP_SOURCE_HARDWARE = "kvaser-hardware"
TIMESTAMP_SOURCE_HOST = "host-receive"


class HardwareTimestampMapper:
    """Map Kvaser timer ticks into the ``perf_counter_ns`` time domain.

    Capture services, markers and the GUI all measure time relative to a
    ``perf_counter_ns()`` origin. Instead of stamping frames with the moment the
    Python reader thread happened to pull them from the driver (which adds OS
    scheduling and GIL jitter, and collapses bursts onto nearly identical
    times), CRT uses the adapter's own receive timestamp and shifts it into the
    host clock domain with one anchor pair taken right after ``busOn``.

    Inter-frame deltas are therefore exactly the hardware deltas. The absolute
    offset to host-side events (markers) is accurate to the anchor uncertainty
    plus the relative drift of both clocks (typically tens of ppm).
    """

    __slots__ = ("_tick_ns", "_hw_anchor", "_host_anchor_ns", "_last_raw", "_wraps")

    def __init__(self, *, tick_ns: int, hw_anchor: int, host_anchor_ns: int) -> None:
        if tick_ns <= 0:
            raise ValueError("tick_ns must be greater than zero")
        self._tick_ns = int(tick_ns)
        self._hw_anchor = int(hw_anchor)
        self._host_anchor_ns = int(host_anchor_ns)
        self._last_raw = int(hw_anchor) % _TIMER_WRAP
        self._wraps = 0

    @property
    def tick_ns(self) -> int:
        return self._tick_ns

    def to_host_ns(self, raw_timestamp: int) -> int:
        raw = int(raw_timestamp)
        if raw < _TIMER_WRAP:
            # Unwrap a 32-bit counter. A large backwards jump means overflow;
            # small backwards steps (should not happen) are kept as-is.
            if raw < self._last_raw and self._last_raw - raw > _TIMER_WRAP // 2:
                self._wraps += 1
            self._last_raw = raw
            raw += self._wraps * _TIMER_WRAP
        return max(0, self._host_anchor_ns + (raw - self._hw_anchor) * self._tick_ns)


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
    """Read-only Kvaser producer with an isolated CANlib receive thread.

    The reader thread owns the complete CANlib handle lifecycle: it opens the
    channel, configures the driver and bitrate, switches the bus on, continuously
    executes ``read(timeout=1)``, and finally switches the bus off and closes the
    handle. No other application thread touches the CANlib channel object.

    Frame ``timestamp_ns`` values come from the adapter's hardware receive
    timestamp (mapped into the ``perf_counter_ns`` domain, see
    :class:`HardwareTimestampMapper`). When the driver does not expose the timer
    controls, CRT falls back to the host receive time and reports this through
    :attr:`timestamp_source`.

    Received frames are copied into an unbounded in-process queue. Disk writes,
    transport reassembly, protocol decoding, filtering and GUI updates consume
    that queue later and therefore cannot delay hardware reads.
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

        self._frames: Queue[CanFrame] = Queue()
        self._reader_stop = Event()
        self._reader_ready = Event()
        self._reader_closed = Event()
        self._reader_thread: Thread | None = None
        self._reader_error: BaseException | None = None
        self._channel_active = False
        self._sequence = 0
        self._received_count = 0
        self._delivered_count = 0
        self._timestamp_source = TIMESTAMP_SOURCE_HOST
        self._timer_resolution_ns: int | None = None

    @property
    def timestamp_source(self) -> str:
        """``kvaser-hardware`` or ``host-receive`` for the current/last capture."""

        return self._timestamp_source

    @property
    def timer_resolution_ns(self) -> int | None:
        """Hardware timer tick in nanoseconds, or ``None`` for host timestamps."""

        return self._timer_resolution_ns

    @property
    def is_open(self) -> bool:
        thread = self._reader_thread
        return bool(self._channel_active and thread is not None and thread.is_alive())

    @property
    def prefetched_count(self) -> int:
        """Frames already removed from CANlib and waiting for analysis."""

        return self._frames.qsize()

    @property
    def received_count(self) -> int:
        """Frames copied from CANlib into the application buffer."""

        return self._received_count

    @property
    def delivered_count(self) -> int:
        """Frames already delivered from the buffer to CaptureService."""

        return self._delivered_count

    def open(self) -> None:
        thread = self._reader_thread
        if thread is not None and thread.is_alive():
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

        self._frames = Queue()
        self._reader_stop = Event()
        self._reader_ready = Event()
        self._reader_closed = Event()
        self._reader_error = None
        self._channel_active = False
        self._sequence = 0
        self._received_count = 0
        self._delivered_count = 0
        self._timestamp_source = TIMESTAMP_SOURCE_HOST
        self._timer_resolution_ns = None

        thread = Thread(
            target=self._receive_loop,
            args=(bitrate_value,),
            name=f"crt-kvaser-rx-{self.channel_number}",
            daemon=True,
        )
        self._reader_thread = thread
        thread.start()

        if not self._reader_ready.wait(READER_START_TIMEOUT_S):
            self._reader_stop.set()
            raise KvaserReceiveError(
                f"Kvaser receive thread did not start within {READER_START_TIMEOUT_S:.1f} s"
            )
        if self._reader_error is not None:
            thread.join(READER_STOP_TIMEOUT_S)
            self._reader_thread = None
            raise KvaserReceiveError(
                f"Could not start Kvaser receive thread: {self._reader_error}"
            ) from self._reader_error
        if not self._channel_active:
            raise KvaserReceiveError("Kvaser receive thread stopped during startup")

    def read(self, timeout_ms: int = 100) -> CanFrame | None:
        """Return a frame already buffered by the isolated reader thread."""

        if self._reader_thread is None:
            raise RuntimeError("Kvaser channel is not open")
        if timeout_ms < 0:
            raise ValueError("timeout_ms cannot be negative")

        try:
            if timeout_ms == 0:
                frame = self._frames.get_nowait()
            else:
                frame = self._frames.get(timeout=timeout_ms / 1000.0)
        except Empty:
            if self._reader_error is not None:
                raise KvaserReceiveError(
                    f"Kvaser receive thread failed: {self._reader_error}"
                ) from self._reader_error
            return None

        self._delivered_count += 1
        return frame

    def _receive_loop(self, bitrate_value: Any) -> None:
        api = _require_canlib()
        channel: Any | None = None
        mapper: HardwareTimestampMapper | None = None

        try:
            # Keep the full CANlib handle lifecycle in this one producer thread,
            # exactly like the known-good standalone monitor.
            channel = api.openChannel(self.channel_number)
            driver = (
                api.Driver.SILENT
                if self.mode is KvaserReceiveMode.LISTEN_ONLY
                else api.Driver.NORMAL
            )
            channel.setBusOutputControl(driver)
            channel.setBusParams(bitrate_value)
            tick_ns = _configure_timer_scale(channel)
            channel.busOn()
            mapper = _anchor_hardware_clock(channel, tick_ns)
            if mapper is not None:
                self._timestamp_source = TIMESTAMP_SOURCE_HARDWARE
                self._timer_resolution_ns = mapper.tick_ns

            self._channel_active = True
            self._reader_ready.set()

            while not self._reader_stop.is_set():
                try:
                    frame = channel.read(timeout=self.driver_read_timeout_ms)
                except api.CanNoMsg:
                    continue

                received_ns = perf_counter_ns()
                flags = frame.flags
                timestamp_ns = received_ns
                if mapper is not None:
                    try:
                        timestamp_ns = mapper.to_host_ns(frame.timestamp)
                    except (TypeError, ValueError):
                        timestamp_ns = received_ns
                captured = CanFrame(
                    sequence=self._sequence,
                    timestamp_ns=timestamp_ns,
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
                self._received_count += 1
                self._frames.put(captured)
        except BaseException as exc:
            if not self._reader_stop.is_set():
                self._reader_error = exc
            self._reader_ready.set()
        finally:
            self._channel_active = False
            if channel is not None:
                try:
                    channel.busOff()
                except Exception:
                    pass
                finally:
                    try:
                        channel.close()
                    except Exception:
                        pass
            self._reader_ready.set()
            self._reader_closed.set()

    def close(self) -> None:
        thread = self._reader_thread
        if thread is None:
            return

        self._reader_stop.set()
        thread.join(READER_STOP_TIMEOUT_S)
        if thread.is_alive():
            raise KvaserReceiveError(
                f"Kvaser receive thread did not stop within {READER_STOP_TIMEOUT_S:.1f} s"
            )
        self._reader_thread = None
        self._channel_active = False

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


def _configure_timer_scale(channel: Any) -> int | None:
    """Request microsecond hardware timestamps; return the tick in ns or ``None``."""

    try:
        iocontrol = channel.iocontrol
        iocontrol.timer_scale = HARDWARE_TIMER_SCALE_US
        scale_us = int(iocontrol.timer_scale)
    except Exception:
        return None
    if scale_us <= 0:
        return None
    return scale_us * 1000


def _anchor_hardware_clock(channel: Any, tick_ns: int | None) -> HardwareTimestampMapper | None:
    """Pair the adapter timer with ``perf_counter_ns`` right after bus-on."""

    if tick_ns is None:
        return None
    try:
        before = perf_counter_ns()
        hw_now = int(channel.readTimer())
        after = perf_counter_ns()
    except Exception:
        return None
    return HardwareTimestampMapper(
        tick_ns=tick_ns,
        hw_anchor=hw_now,
        host_anchor_ns=(before + after) // 2,
    )
