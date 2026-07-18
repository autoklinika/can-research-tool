from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.live_performance import (
    InstrumentedLiveCaptureController,
    maybe_instrument_live_controller,
)


class _Clock:
    def __init__(self, step_ns: int = 100_000_000) -> None:
        self.value = 0
        self.step = step_ns

    def __call__(self) -> int:
        self.value += self.step
        return self.value


@dataclass
class _Request:
    channel_number: int = 0
    bitrate: int = 250_000
    mode: str = "bench"
    session_name: str = "bench test"
    output_dir: Path = Path("sessions")
    persist_to_disk: bool = True


class _FakeController:
    def __init__(self) -> None:
        self.active = True
        self.status_index = 0

    def start(self, _request):
        return SimpleNamespace(session=Path("sessions/test.crt.jsonl"))

    def status(self):
        states = ("running", "running", "stopped")
        state = states[min(self.status_index, len(states) - 1)]
        self.status_index += 1
        total = self.status_index * 100
        return SimpleNamespace(
            state=state,
            elapsed_s=float(self.status_index),
            frame_count=total,
            logical_message_count=total // 10,
            live_capacity=250_000,
            live_retained=total,
            live_dropped_from_view=0,
            live_message_capacity=100_000,
            live_messages_retained=total // 10,
            live_messages_dropped_from_view=0,
        )

    def frames_since(self, _after_sequence):
        return SimpleNamespace(frames=(1, 2, 3), truncated=False)

    def messages_since(self, _after_sequence):
        return SimpleNamespace(messages=(1,), truncated=False)

    def stop(self) -> None:
        self.active = False

    def wait(self, _timeout=None) -> bool:
        return True

    def list_adapters(self):
        return []

    def add_marker(self, preset, *, source="keyboard", note=""):
        return preset, source, note

    @property
    def is_active(self) -> bool:
        return self.active


def test_disabled_factory_preserves_controller(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CRT_LIVE_PERF", raising=False)
    controller = _FakeController()

    result = maybe_instrument_live_controller(controller, report_dir=tmp_path)

    assert result is controller


def test_enabled_factory_wraps_controller(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CRT_LIVE_PERF", "1")
    monkeypatch.setenv("CRT_LIVE_PERF_INTERVAL_S", "0.5")
    controller = _FakeController()

    result = maybe_instrument_live_controller(controller, report_dir=tmp_path)

    assert isinstance(result, InstrumentedLiveCaptureController)


def test_report_contains_rates_batches_and_resources(tmp_path: Path) -> None:
    wall = _Clock()
    cpu = _Clock(step_ns=20_000_000)
    controller = InstrumentedLiveCaptureController(
        _FakeController(),
        report_dir=tmp_path,
        sample_interval_s=0.25,
        clock_ns=wall,
        process_clock_ns=cpu,
        rss_reader=lambda: (123_456, "test"),
        utc_now=lambda: datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
    )

    controller.start(_Request())
    for frame_cursor, message_cursor in ((None, None), (3, 1), (6, 2)):
        controller.status()
        controller.frames_since(frame_cursor)
        controller.messages_since(message_cursor)

    report_path = controller.report_path
    assert report_path is not None
    records = [
        json.loads(line)
        for line in report_path.read_text(encoding="utf-8").splitlines()
    ]
    kinds = [record["record"] for record in records]
    samples = [record for record in records if record["record"] == "sample"]

    assert kinds[0] == "report_started"
    assert "capture_started" in kinds
    assert kinds.count("capture_finished") == 1
    assert kinds[-1] == "report_closed"
    assert samples
    assert all(sample["process"]["memory_bytes"] == 123_456 for sample in samples)
    assert max(sample["batches"]["frames"]["records"] for sample in samples) >= 3
    assert max(sample["batches"]["messages"]["records"] for sample in samples) >= 1
    assert samples[-1]["capture"]["state"] == "stopped"
