from pathlib import Path
from time import perf_counter_ns, sleep

from app.capture_service import CaptureConfig, CaptureService, CaptureState
from app.models import CanFrame
from kvaser.backend import KvaserChannelInfo, KvaserReceiveMode


class FakeChannel:
    def __init__(self) -> None:
        base = perf_counter_ns()
        self._frames = [
            CanFrame(
                sequence=sequence,
                timestamp_ns=base + sequence * 1_000_000,
                arbitration_id=0x100 + sequence,
                data=bytes([sequence]),
            )
            for sequence in range(3)
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self, timeout_ms: int = 100) -> CanFrame | None:
        if self._frames:
            return self._frames.pop(0)
        sleep(0.001)
        return None


def test_capture_service_streams_to_disk_and_bounds_live_view(tmp_path: Path) -> None:
    def channel_factory(**kwargs):
        assert kwargs["channel_number"] == 0
        assert kwargs["bitrate"] == 250_000
        assert kwargs["mode"] is KvaserReceiveMode.BENCH
        return FakeChannel()

    def channel_provider():
        return [
            KvaserChannelInfo(
                number=0,
                name="Fake Kvaser",
                serial_number="123",
                product_number="00-00000-00000-0",
                supports_silent_mode=True,
            )
        ]

    service = CaptureService(
        channel_factory=channel_factory,
        channel_provider=channel_provider,
    )
    paths = service.start(
        CaptureConfig(
            channel_number=0,
            bitrate=250_000,
            mode=KvaserReceiveMode.BENCH,
            session_name="service-test",
            output_dir=tmp_path,
            duration_s=0.03,
            live_buffer_capacity=2,
        )
    )

    assert service.wait(2.0) is True
    status = service.status()
    assert status.state is CaptureState.STOPPED
    assert status.frame_count == 3
    assert status.logical_message_count == 3
    assert status.unique_can_ids == 3
    assert status.live_retained == 2
    assert status.live_dropped_from_view == 1

    snapshot = service.live_snapshot_since(None)
    assert [frame.sequence for frame in snapshot.frames] == [1, 2]
    assert paths.session.exists()
    assert paths.raw_frames_csv.exists()
    assert paths.logical_messages_csv.exists()
    assert paths.session.with_suffix(paths.session.suffix + ".idx.json").exists()
