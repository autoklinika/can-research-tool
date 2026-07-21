from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable

from kvaser.backend import (
    KvaserChannelInfo,
    KvaserReceiveMode,
    list_channels,
)

from .capture_service import (
    CaptureConfig,
    CapturePaths,
    CaptureService,
    CaptureStatus,
)
from .deferred_capture_service import DeferredLogicalCaptureService
from .live_buffer import LiveFrameSnapshot
from .live_message_buffer import LiveMessageSnapshot
from .markers import CaptureMarker, MarkerPreset


class CaptureMode(StrEnum):
    """Receive modes exposed to presentation code without backend types."""

    BENCH = "bench"
    LISTEN_ONLY = "listen-only"


@dataclass(frozen=True, slots=True)
class CanAdapterInfo:
    """Backend-neutral adapter description used by Live Capture views."""

    number: int
    name: str
    serial_number: str
    product_number: str
    supports_silent_mode: bool
    is_virtual: bool


@dataclass(frozen=True, slots=True)
class StartCaptureRequest:
    """Application-layer request translated to ``CaptureConfig`` by the controller."""

    channel_number: int
    bitrate: int
    mode: CaptureMode
    session_name: str
    output_dir: Path
    persist_to_disk: bool = True
    live_buffer_capacity: int = 20_000
    live_message_capacity: int = 5_000
    marker_presets: tuple[MarkerPreset, ...] = ()


CaptureServiceFactory = Callable[..., CaptureService]
ChannelProvider = Callable[[], list[KvaserChannelInfo]]


class LiveCaptureController:
    """Application boundary for raw-only Live Capture lifecycle and snapshots."""

    def __init__(
        self,
        *,
        service_factory: CaptureServiceFactory = DeferredLogicalCaptureService,
        channel_provider: ChannelProvider = list_channels,
    ) -> None:
        self._channel_provider = channel_provider
        self._service = service_factory(channel_provider=channel_provider)

    def list_adapters(self) -> list[CanAdapterInfo]:
        return [
            CanAdapterInfo(
                number=channel.number,
                name=channel.name,
                serial_number=channel.serial_number,
                product_number=channel.product_number,
                supports_silent_mode=channel.supports_silent_mode,
                is_virtual="Virtual CAN Driver" in channel.name,
            )
            for channel in self._channel_provider()
        ]

    def start(self, request: StartCaptureRequest) -> CapturePaths | None:
        config = CaptureConfig(
            channel_number=int(request.channel_number),
            bitrate=int(request.bitrate),
            mode=KvaserReceiveMode(CaptureMode(request.mode).value),
            session_name=request.session_name,
            output_dir=Path(request.output_dir),
            persist_to_disk=bool(request.persist_to_disk),
            live_buffer_capacity=int(request.live_buffer_capacity),
            live_message_capacity=int(request.live_message_capacity),
            marker_presets=tuple(request.marker_presets),
        )
        return self._service.start(config)

    def stop(self) -> None:
        self._service.stop()

    def wait(self, timeout: float | None = None) -> bool:
        return self._service.wait(timeout)

    def status(self) -> CaptureStatus:
        return self._service.status()

    def frames_since(self, after_sequence: int | None) -> LiveFrameSnapshot:
        return self._service.live_snapshot_since(after_sequence)

    def messages_since(self, after_sequence: int | None) -> LiveMessageSnapshot:
        """Compatibility API; production Live no longer consumes this snapshot."""

        return self._service.live_messages_snapshot_since(after_sequence)

    def add_marker(
        self,
        preset: MarkerPreset,
        *,
        source: str = "keyboard",
        note: str = "",
    ) -> CaptureMarker:
        return self._service.add_marker(preset, source=source, note=note)

    @property
    def is_active(self) -> bool:
        return self._service.is_active
