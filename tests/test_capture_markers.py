from pathlib import Path
from time import perf_counter_ns, sleep

from app.capture_service import CaptureConfig, CaptureService, CaptureState
from app.marker_stream import iter_markers
from app.markers import MarkerPreset
from app.models import CanFrame
from kvaser.backend import KvaserChannelInfo, KvaserReceiveMode


class SlowFakeChannel:
    def __init__(self) -> None:
        self._base = perf_counter_ns()
        self._sequence = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self, timeout_ms: int = 100) -> CanFrame | None:
        sleep(0.002)
        frame = CanFrame(
            sequence=self._sequence,
            timestamp_ns=perf_counter_ns(),
            arbitration_id=0x123,
            data=bytes([self._sequence & 0xFF]),
        )
        self._sequence += 1
        return frame


def test_marker_is_timestamped_and_written_during_capture(tmp_path: Path) -> None:
    service = CaptureService(
        channel_factory=lambda **kwargs: SlowFakeChannel(),
        channel_provider=lambda: [
            KvaserChannelInfo(
                number=0,
                name="Fake Kvaser",
                serial_number="1",
                product_number="test",
                supports_silent_mode=True,
            )
        ],
    )
    preset = MarkerPreset.create("EGR odłączony", "F3", area="EGR")
    paths = service.start(
        CaptureConfig(
            channel_number=0,
            bitrate=250_000,
            mode=KvaserReceiveMode.BENCH,
            session_name="marker-test",
            output_dir=tmp_path,
            duration_s=0.08,
            marker_presets=(preset,),
        )
    )

    for _ in range(100):
        if service.status().state is CaptureState.RUNNING:
            break
        sleep(0.002)
    marker = service.add_marker(preset, source="keyboard")

    assert service.wait(2.0)
    status = service.status()
    assert status.state is CaptureState.STOPPED
    assert status.marker_count == 1
    assert marker.timestamp_ns >= 0
    assert list(iter_markers(paths.markers)) == [marker]
