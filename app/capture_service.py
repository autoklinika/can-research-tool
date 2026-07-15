from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from queue import Empty, Queue
from threading import Event, RLock, Thread
from time import monotonic, perf_counter_ns
from typing import Callable, ContextManager, Protocol

from kvaser.backend import (
    KvaserChannelInfo,
    KvaserPassiveChannel,
    KvaserReceiveMode,
    list_channels,
)

from .live_buffer import LiveFrameBuffer, LiveFrameSnapshot
from .marker_stream import MarkerStreamWriter
from .markers import CaptureMarker, MarkerPreset
from .models import CanFrame, CaptureSession
from .protocols import ProtocolRegistry
from .session_stream import SessionStreamWriter
from .stream_exports import FrameCsvStreamWriter, MessageCsvStreamWriter
from .stream_pipeline import StreamingTransportPipeline


class ReadableCanChannel(Protocol):
    def read(self, timeout_ms: int = 100) -> CanFrame | None: ...


ChannelFactory = Callable[..., ContextManager[ReadableCanChannel]]
ChannelProvider = Callable[[], list[KvaserChannelInfo]]


class CaptureState(StrEnum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class CaptureConfig:
    channel_number: int = 0
    bitrate: int = 250_000
    mode: KvaserReceiveMode = KvaserReceiveMode.BENCH
    session_name: str = ""
    output_dir: Path = Path("sessions")
    duration_s: float | None = None
    live_buffer_capacity: int = 20_000
    read_timeout_ms: int = 50
    writer_flush_every: int = 256
    marker_presets: tuple[MarkerPreset, ...] = ()

    def __post_init__(self) -> None:
        if self.channel_number < 0:
            raise ValueError("channel_number cannot be negative")
        if self.bitrate <= 0:
            raise ValueError("bitrate must be greater than zero")
        if self.duration_s is not None and self.duration_s <= 0:
            raise ValueError("duration_s must be greater than zero or None")
        if self.live_buffer_capacity <= 0:
            raise ValueError("live_buffer_capacity must be greater than zero")
        if self.read_timeout_ms < 0:
            raise ValueError("read_timeout_ms cannot be negative")
        if self.writer_flush_every <= 0:
            raise ValueError("writer_flush_every must be greater than zero")
        shortcuts = [
            preset.shortcut.strip().lower()
            for preset in self.marker_presets
            if preset.enabled
        ]
        if len(shortcuts) != len(set(shortcuts)):
            raise ValueError("active marker shortcuts must be unique")


@dataclass(frozen=True, slots=True)
class CapturePaths:
    session: Path
    raw_frames_csv: Path
    logical_messages_csv: Path
    markers: Path


@dataclass(frozen=True, slots=True)
class CaptureStatus:
    state: CaptureState
    elapsed_s: float
    frame_count: int
    logical_message_count: int
    incomplete_message_count: int
    marker_count: int
    unique_can_ids: int
    adapter_name: str
    error: str
    paths: CapturePaths | None
    live_capacity: int
    live_retained: int
    live_dropped_from_view: int
    last_marker: CaptureMarker | None


class CaptureService:
    """Background Kvaser capture with bounded GUI state and precise markers."""

    def __init__(
        self,
        *,
        channel_factory: ChannelFactory = KvaserPassiveChannel,
        channel_provider: ChannelProvider = list_channels,
    ) -> None:
        self._channel_factory = channel_factory
        self._channel_provider = channel_provider
        self._lock = RLock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._live_buffer = LiveFrameBuffer()
        self._marker_queue: Queue[CaptureMarker] = Queue()
        self._state = CaptureState.IDLE
        self._started_monotonic: float | None = None
        self._capture_origin_ns: int | None = None
        self._completed_elapsed_s = 0.0
        self._frame_count = 0
        self._logical_message_count = 0
        self._incomplete_message_count = 0
        self._marker_count = 0
        self._unique_can_ids = 0
        self._adapter_name = ""
        self._error = ""
        self._paths: CapturePaths | None = None
        self._last_marker: CaptureMarker | None = None

    def start(self, config: CaptureConfig) -> CapturePaths:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("capture is already running")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            requested_name = config.session_name.strip() or f"capture_{timestamp}"
            safe_name = _safe_filename(requested_name)
            output_dir = Path(config.output_dir)
            paths = CapturePaths(
                session=output_dir / f"{safe_name}.crt.jsonl",
                raw_frames_csv=output_dir / f"{safe_name}.frames.csv",
                logical_messages_csv=output_dir / f"{safe_name}.messages.csv",
                markers=output_dir / f"{safe_name}.markers.jsonl",
            )

            self._stop_event = Event()
            self._live_buffer = LiveFrameBuffer(config.live_buffer_capacity)
            self._marker_queue = Queue()
            self._state = CaptureState.STARTING
            self._started_monotonic = None
            self._capture_origin_ns = None
            self._completed_elapsed_s = 0.0
            self._frame_count = 0
            self._logical_message_count = 0
            self._incomplete_message_count = 0
            self._marker_count = 0
            self._unique_can_ids = 0
            self._adapter_name = ""
            self._error = ""
            self._paths = paths
            self._last_marker = None
            self._thread = Thread(
                target=self._run,
                args=(config, requested_name, paths),
                name="crt-capture-worker",
                daemon=True,
            )
            self._thread.start()
            return paths

    def stop(self) -> None:
        with self._lock:
            if self._state in (CaptureState.STARTING, CaptureState.RUNNING):
                self._state = CaptureState.STOPPING
            self._stop_event.set()

    def wait(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def add_marker(
        self,
        preset: MarkerPreset,
        *,
        source: str = "keyboard",
        note: str = "",
    ) -> CaptureMarker:
        """Timestamp a marker immediately and queue its disk write."""

        with self._lock:
            if self._state is not CaptureState.RUNNING or self._capture_origin_ns is None:
                raise RuntimeError("markers can be added only while capture is running")
            timestamp_ns = max(0, perf_counter_ns() - self._capture_origin_ns)
        marker = CaptureMarker.from_preset(
            preset,
            timestamp_ns,
            source=source,
            note=note,
        )
        self._marker_queue.put(marker)
        with self._lock:
            self._last_marker = marker
        return marker

    def status(self) -> CaptureStatus:
        live = self._live_buffer.snapshot_since(None)
        with self._lock:
            if self._started_monotonic is not None and self._state in (
                CaptureState.RUNNING,
                CaptureState.STOPPING,
            ):
                elapsed = monotonic() - self._started_monotonic
            else:
                elapsed = self._completed_elapsed_s
            return CaptureStatus(
                state=self._state,
                elapsed_s=max(0.0, elapsed),
                frame_count=self._frame_count,
                logical_message_count=self._logical_message_count,
                incomplete_message_count=self._incomplete_message_count,
                marker_count=self._marker_count,
                unique_can_ids=self._unique_can_ids,
                adapter_name=self._adapter_name,
                error=self._error,
                paths=self._paths,
                live_capacity=live.capacity,
                live_retained=(
                    0
                    if live.first_available_sequence is None
                    else live.total_received - live.dropped_from_view
                ),
                live_dropped_from_view=live.dropped_from_view,
                last_marker=self._last_marker,
            )

    def live_snapshot_since(self, after_sequence: int | None) -> LiveFrameSnapshot:
        return self._live_buffer.snapshot_since(after_sequence)

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._state in (
                CaptureState.STARTING,
                CaptureState.RUNNING,
                CaptureState.STOPPING,
            )

    def _run(
        self,
        config: CaptureConfig,
        requested_name: str,
        paths: CapturePaths,
    ) -> None:
        session_writer: SessionStreamWriter | None = None
        frame_writer: FrameCsvStreamWriter | None = None
        message_writer: MessageCsvStreamWriter | None = None
        marker_writer: MarkerStreamWriter | None = None
        started = monotonic()
        local_frame_count = 0
        local_message_count = 0
        local_incomplete_count = 0
        local_marker_count = 0
        unique_ids: set[tuple[int, bool]] = set()
        pending_live: list[CanFrame] = []

        try:
            channels = self._channel_provider()
            channel_info = next(
                (item for item in channels if item.number == config.channel_number),
                None,
            )
            if channel_info is None:
                available = ", ".join(str(item.number) for item in channels) or "none"
                raise RuntimeError(
                    f"Kvaser channel {config.channel_number} was not found; available: {available}"
                )

            session = CaptureSession(
                name=requested_name,
                source="kvaser-live-stream",
                bitrate=config.bitrate,
                channel=config.channel_number,
                adapter=channel_info.name,
                metadata={
                    "receive_mode": KvaserReceiveMode(config.mode).value,
                    "serial_number": channel_info.serial_number,
                    "product_number": channel_info.product_number,
                    "streaming_capture": True,
                    "live_buffer_capacity": config.live_buffer_capacity,
                    "requested_duration_s": config.duration_s,
                    "marker_presets": [preset.to_dict() for preset in config.marker_presets],
                    "marker_stream": paths.markers.name,
                },
            )
            session_writer = SessionStreamWriter(
                session,
                paths.session,
                flush_every=config.writer_flush_every,
            )
            frame_writer = FrameCsvStreamWriter(
                paths.raw_frames_csv,
                flush_every=config.writer_flush_every,
            )
            message_writer = MessageCsvStreamWriter(paths.logical_messages_csv)
            marker_writer = MarkerStreamWriter(
                paths.markers,
                presets=config.marker_presets,
                flush_every=1,
            )
            session_writer.open()
            frame_writer.open()
            message_writer.open()
            marker_writer.open()

            pipeline = StreamingTransportPipeline()
            protocols = ProtocolRegistry()
            capture_origin_ns = perf_counter_ns()
            deadline = (
                None
                if config.duration_s is None
                else monotonic() + config.duration_s
            )
            next_publish = monotonic() + 0.1

            with self._channel_factory(
                channel_number=config.channel_number,
                bitrate=config.bitrate,
                mode=KvaserReceiveMode(config.mode),
            ) as channel:
                started = monotonic()
                with self._lock:
                    self._state = CaptureState.RUNNING
                    self._started_monotonic = started
                    self._capture_origin_ns = capture_origin_ns
                    self._adapter_name = channel_info.name

                while not self._stop_event.is_set() and (
                    deadline is None or monotonic() < deadline
                ):
                    frame = channel.read(timeout_ms=config.read_timeout_ms)
                    now = monotonic()
                    if frame is not None:
                        normalized = replace(
                            frame,
                            timestamp_ns=max(0, frame.timestamp_ns - capture_origin_ns),
                        )
                        session_writer.append(normalized)
                        frame_writer.append(normalized)
                        pending_live.append(normalized)
                        local_frame_count += 1
                        unique_ids.add(
                            (normalized.arbitration_id, normalized.is_extended_id)
                        )

                        for message in pipeline.feed(normalized):
                            decoded = protocols.decode(message)
                            message_writer.append(decoded)
                            local_message_count += 1
                            if not message.complete:
                                local_incomplete_count += 1

                    local_marker_count += self._drain_markers(marker_writer)

                    if len(pending_live) >= 256 or now >= next_publish:
                        if pending_live:
                            self._live_buffer.append_many(pending_live)
                            pending_live.clear()
                        self._publish_progress(
                            local_frame_count,
                            local_message_count,
                            local_incomplete_count,
                            local_marker_count,
                            len(unique_ids),
                        )
                        next_publish = now + 0.1

            local_marker_count += self._drain_markers(marker_writer)
            for message in pipeline.flush():
                decoded = protocols.decode(message)
                message_writer.append(decoded)
                local_message_count += 1
                if not message.complete:
                    local_incomplete_count += 1

            if pending_live:
                self._live_buffer.append_many(pending_live)
                pending_live.clear()

            elapsed = monotonic() - started
            final_metadata = {
                "actual_duration_s": round(elapsed, 6),
                "frame_count": local_frame_count,
                "logical_message_count": local_message_count,
                "incomplete_message_count": local_incomplete_count,
                "marker_count": local_marker_count,
                "unique_can_ids": len(unique_ids),
                "clean_close": True,
            }
            session_writer.close(final_metadata)
            session_writer = None
            frame_writer.close()
            frame_writer = None
            message_writer.close()
            message_writer = None
            marker_writer.close()
            marker_writer = None

            self._publish_progress(
                local_frame_count,
                local_message_count,
                local_incomplete_count,
                local_marker_count,
                len(unique_ids),
            )
            with self._lock:
                self._state = CaptureState.STOPPED
                self._completed_elapsed_s = elapsed
                self._started_monotonic = None
                self._capture_origin_ns = None
        except Exception as exc:
            if pending_live:
                self._live_buffer.append_many(pending_live)
            elapsed = monotonic() - started
            if marker_writer is not None:
                try:
                    local_marker_count += self._drain_markers(marker_writer)
                finally:
                    marker_writer.close()
            if session_writer is not None:
                session_writer.close(
                    {
                        "actual_duration_s": round(elapsed, 6),
                        "frame_count": local_frame_count,
                        "logical_message_count": local_message_count,
                        "incomplete_message_count": local_incomplete_count,
                        "marker_count": local_marker_count,
                        "unique_can_ids": len(unique_ids),
                        "clean_close": False,
                        "capture_error": str(exc),
                    }
                )
            if frame_writer is not None:
                frame_writer.close()
            if message_writer is not None:
                message_writer.close()
            self._publish_progress(
                local_frame_count,
                local_message_count,
                local_incomplete_count,
                local_marker_count,
                len(unique_ids),
            )
            with self._lock:
                self._state = CaptureState.ERROR
                self._error = str(exc)
                self._completed_elapsed_s = elapsed
                self._started_monotonic = None
                self._capture_origin_ns = None

    def _drain_markers(self, writer: MarkerStreamWriter) -> int:
        count = 0
        while True:
            try:
                marker = self._marker_queue.get_nowait()
            except Empty:
                break
            writer.append(marker)
            count += 1
        return count

    def _publish_progress(
        self,
        frame_count: int,
        message_count: int,
        incomplete_count: int,
        marker_count: int,
        unique_can_ids: int,
    ) -> None:
        with self._lock:
            self._frame_count = frame_count
            self._logical_message_count = message_count
            self._incomplete_message_count = incomplete_count
            self._marker_count = marker_count
            self._unique_can_ids = unique_can_ids


def _safe_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return sanitized or "capture"
