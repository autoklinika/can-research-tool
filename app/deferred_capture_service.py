from __future__ import annotations

from dataclasses import replace
from time import monotonic, perf_counter_ns

from kvaser.backend import KvaserReceiveMode

from .capture_service import CaptureConfig, CapturePaths, CaptureService, CaptureState
from .marker_stream import MarkerStreamWriter
from .models import CanFrame, CaptureSession
from .session_stream import SessionStreamWriter
from .stream_exports import FrameCsvStreamWriter


class DeferredLogicalCaptureService(CaptureService):
    """Capture full raw traffic without constructing logical messages in realtime.

    The completed ``*.crt.jsonl`` remains fully compatible with the stored-session
    analysis pipeline. When the operator presses ``Załaduj``, the existing logical
    cache worker reconstructs transport and protocol messages from raw frames in a
    separate process. Kvaser lifecycle and raw-frame write ordering are unchanged.
    """

    def _run(
        self,
        config: CaptureConfig,
        requested_name: str,
        paths: CapturePaths | None,
    ) -> None:
        session_writer: SessionStreamWriter | None = None
        frame_writer: FrameCsvStreamWriter | None = None
        marker_writer: MarkerStreamWriter | None = None
        started = monotonic()
        local_frame_count = 0
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

            if paths is not None:
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
                        "deferred_logical_analysis": True,
                        "live_buffer_capacity": config.live_buffer_capacity,
                        "requested_duration_s": config.duration_s,
                        "marker_presets": [
                            preset.to_dict() for preset in config.marker_presets
                        ],
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
                marker_writer = MarkerStreamWriter(
                    paths.markers,
                    presets=config.marker_presets,
                    flush_every=1,
                )
                session_writer.open()
                frame_writer.open()
                marker_writer.open()

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
                        if session_writer is not None:
                            session_writer.append(normalized)
                        if frame_writer is not None:
                            frame_writer.append(normalized)
                        pending_live.append(normalized)
                        local_frame_count += 1
                        unique_ids.add(
                            (normalized.arbitration_id, normalized.is_extended_id)
                        )

                    local_marker_count += self._drain_markers(marker_writer)

                    if len(pending_live) >= 256 or now >= next_publish:
                        if pending_live:
                            self._live_buffer.append_many(pending_live)
                            pending_live.clear()
                        self._publish_progress(
                            local_frame_count,
                            0,
                            0,
                            local_marker_count,
                            len(unique_ids),
                        )
                        next_publish = now + 0.1

            local_marker_count += self._drain_markers(marker_writer)
            if pending_live:
                self._live_buffer.append_many(pending_live)
                pending_live.clear()

            elapsed = monotonic() - started
            final_metadata = {
                "actual_duration_s": round(elapsed, 6),
                "frame_count": local_frame_count,
                "logical_message_count": 0,
                "logical_analysis_deferred": True,
                "incomplete_message_count": 0,
                "marker_count": local_marker_count,
                "unique_can_ids": len(unique_ids),
                "clean_close": True,
            }
            if session_writer is not None:
                session_writer.close(final_metadata)
                session_writer = None
            if frame_writer is not None:
                frame_writer.close()
                frame_writer = None
            if marker_writer is not None:
                marker_writer.close()
                marker_writer = None

            self._publish_progress(
                local_frame_count,
                0,
                0,
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
            try:
                local_marker_count += self._drain_markers(marker_writer)
            finally:
                if marker_writer is not None:
                    marker_writer.close()
            if session_writer is not None:
                session_writer.close(
                    {
                        "actual_duration_s": round(elapsed, 6),
                        "frame_count": local_frame_count,
                        "logical_message_count": 0,
                        "logical_analysis_deferred": True,
                        "incomplete_message_count": 0,
                        "marker_count": local_marker_count,
                        "unique_can_ids": len(unique_ids),
                        "clean_close": False,
                        "capture_error": str(exc),
                    }
                )
            if frame_writer is not None:
                frame_writer.close()
            self._publish_progress(
                local_frame_count,
                0,
                0,
                local_marker_count,
                len(unique_ids),
            )
            with self._lock:
                self._state = CaptureState.ERROR
                self._error = str(exc)
                self._completed_elapsed_s = elapsed
                self._started_monotonic = None
                self._capture_origin_ns = None
