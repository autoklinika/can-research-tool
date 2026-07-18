from __future__ import annotations

import atexit
import ctypes
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from typing import Callable

from .live_capture_controller import LiveCaptureController, StartCaptureRequest

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_TERMINAL_STATES = frozenset({"stopped", "error"})


@dataclass(slots=True)
class _MetricWindow:
    count: int = 0
    total_ns: int = 0
    max_ns: int = 0

    def add(self, duration_ns: int) -> None:
        duration = max(0, int(duration_ns))
        self.count += 1
        self.total_ns += duration
        self.max_ns = max(self.max_ns, duration)

    def snapshot_ms(self) -> dict[str, float | int]:
        average_ms = self.total_ns / self.count / 1_000_000 if self.count else 0.0
        return {
            "count": self.count,
            "average_ms": round(average_ms, 3),
            "max_ms": round(self.max_ns / 1_000_000, 3),
        }

    def reset(self) -> None:
        self.count = 0
        self.total_ns = 0
        self.max_ns = 0


@dataclass(slots=True)
class _BatchWindow:
    calls: int = 0
    records: int = 0
    max_records: int = 0
    truncations: int = 0

    def add(self, count: int, *, truncated: bool) -> None:
        normalized = max(0, int(count))
        self.calls += 1
        self.records += normalized
        self.max_records = max(self.max_records, normalized)
        self.truncations += int(bool(truncated))

    def snapshot(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "records": self.records,
            "max_records": self.max_records,
            "truncations": self.truncations,
        }

    def reset(self) -> None:
        self.calls = 0
        self.records = 0
        self.max_records = 0
        self.truncations = 0


@dataclass(slots=True)
class _PerformanceWindow:
    operations: dict[str, _MetricWindow] = field(
        default_factory=lambda: {
            "status": _MetricWindow(),
            "frames_since": _MetricWindow(),
            "messages_since": _MetricWindow(),
        }
    )
    poll_intervals: _MetricWindow = field(default_factory=_MetricWindow)
    frame_batches: _BatchWindow = field(default_factory=_BatchWindow)
    message_batches: _BatchWindow = field(default_factory=_BatchWindow)

    def reset(self) -> None:
        for metric in self.operations.values():
            metric.reset()
        self.poll_intervals.reset()
        self.frame_batches.reset()
        self.message_batches.reset()


class InstrumentedLiveCaptureController:
    """Temporary Stage H decorator for Live Capture measurements.

    The decorator observes application-boundary calls only. It does not alter
    ``CaptureService``, Kvaser/CANlib, raw persistence, or any GUI widget.
    """

    def __init__(
        self,
        controller: LiveCaptureController,
        *,
        report_dir: Path,
        sample_interval_s: float = 1.0,
        clock_ns: Callable[[], int] = perf_counter_ns,
        process_clock_ns: Callable[[], int] = process_time_ns,
        rss_reader: Callable[[], tuple[int | None, str]] | None = None,
        utc_now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._controller = controller
        self._report_dir = Path(report_dir)
        self._sample_interval_ns = max(250_000_000, int(sample_interval_s * 1_000_000_000))
        self._clock_ns = clock_ns
        self._process_clock_ns = process_clock_ns
        self._rss_reader = rss_reader or _read_process_memory
        self._utc_now = utc_now
        self._window = _PerformanceWindow()
        self._handle = None
        self._report_path: Path | None = None
        self._report_started_ns: int | None = None
        self._last_sample_ns: int | None = None
        self._last_poll_ns: int | None = None
        self._last_process_wall_ns: int | None = None
        self._last_process_cpu_ns: int | None = None
        self._last_frame_total = 0
        self._last_message_total = 0
        self._latest_status = None
        self._terminal_pending = False
        self._closed = False
        atexit.register(self.close)

    @property
    def report_path(self) -> Path | None:
        return self._report_path

    def list_adapters(self):
        return self._controller.list_adapters()

    def start(self, request: StartCaptureRequest):
        self.close()
        self._closed = False
        self._open_report(request)
        started_ns = self._clock_ns()
        try:
            paths = self._controller.start(request)
        except Exception as exc:
            self._write_record(
                {
                    "record": "start_failed",
                    "duration_ms": round((self._clock_ns() - started_ns) / 1_000_000, 3),
                    "error": str(exc),
                }
            )
            self.close()
            raise
        self._write_record(
            {
                "record": "capture_started",
                "duration_ms": round((self._clock_ns() - started_ns) / 1_000_000, 3),
                "persist_to_disk": bool(request.persist_to_disk),
                "session_path": str(paths.session) if paths is not None else None,
            }
        )
        return paths

    def stop(self) -> None:
        self._write_record({"record": "stop_requested"})
        self._controller.stop()

    def wait(self, timeout: float | None = None) -> bool:
        completed = self._controller.wait(timeout)
        if completed:
            self._finalize_report("wait_completed")
        return completed

    def status(self):
        now_ns = self._clock_ns()
        if self._last_poll_ns is not None:
            self._window.poll_intervals.add(now_ns - self._last_poll_ns)
        self._last_poll_ns = now_ns

        started_ns = self._clock_ns()
        status = self._controller.status()
        self._window.operations["status"].add(self._clock_ns() - started_ns)
        self._latest_status = status
        self._emit_sample_if_due(self._clock_ns(), status)

        state = _state_value(status)
        if state in _TERMINAL_STATES:
            if self._terminal_pending:
                self._finalize_report("terminal_state_confirmed")
            else:
                self._terminal_pending = True
        else:
            self._terminal_pending = False
        return status

    def frames_since(self, after_sequence: int | None):
        started_ns = self._clock_ns()
        snapshot = self._controller.frames_since(after_sequence)
        self._window.operations["frames_since"].add(self._clock_ns() - started_ns)
        self._window.frame_batches.add(
            len(snapshot.frames),
            truncated=bool(snapshot.truncated),
        )
        return snapshot

    def messages_since(self, after_sequence: int | None):
        started_ns = self._clock_ns()
        snapshot = self._controller.messages_since(after_sequence)
        self._window.operations["messages_since"].add(self._clock_ns() - started_ns)
        self._window.message_batches.add(
            len(snapshot.messages),
            truncated=bool(snapshot.truncated),
        )
        if self._terminal_pending:
            self._finalize_report("terminal_snapshot_completed")
        return snapshot

    def add_marker(self, preset, *, source: str = "keyboard", note: str = ""):
        return self._controller.add_marker(preset, source=source, note=note)

    @property
    def is_active(self) -> bool:
        return self._controller.is_active

    def close(self) -> None:
        if self._closed:
            return
        if self._handle is not None:
            self._emit_sample_if_due(self._clock_ns(), self._latest_status, force=True)
            self._write_record({"record": "report_closed"})
            self._handle.close()
        self._handle = None
        self._closed = True

    def _open_report(self, request: StartCaptureRequest) -> None:
        self._report_dir.mkdir(parents=True, exist_ok=True)
        now = self._utc_now()
        safe_session = _safe_component(request.session_name) or "capture"
        requested_path = self._report_dir / (
            f"live-performance-{now:%Y%m%d_%H%M%S}-{safe_session}.jsonl"
        )
        self._report_path = _unique_path(requested_path)
        self._handle = self._report_path.open("x", encoding="utf-8", buffering=1)
        started_ns = self._clock_ns()
        process_cpu_ns = self._process_clock_ns()
        self._report_started_ns = started_ns
        self._last_sample_ns = started_ns
        self._last_poll_ns = None
        self._last_process_wall_ns = started_ns
        self._last_process_cpu_ns = process_cpu_ns
        self._last_frame_total = 0
        self._last_message_total = 0
        self._latest_status = None
        self._terminal_pending = False
        self._window.reset()
        self._write_record(
            {
                "record": "report_started",
                "stage": "H",
                "session_name": request.session_name,
                "channel_number": int(request.channel_number),
                "bitrate": int(request.bitrate),
                "mode": getattr(request.mode, "value", str(request.mode)),
                "sample_interval_s": self._sample_interval_ns / 1_000_000_000,
            }
        )

    def _emit_sample_if_due(self, now_ns: int, status, *, force: bool = False) -> None:
        if self._handle is None or self._last_sample_ns is None:
            return
        elapsed_ns = now_ns - self._last_sample_ns
        if not force and elapsed_ns < self._sample_interval_ns:
            return
        if elapsed_ns <= 0:
            return

        elapsed_s = elapsed_ns / 1_000_000_000
        frame_total = int(getattr(status, "frame_count", self._last_frame_total))
        message_total = int(
            getattr(status, "logical_message_count", self._last_message_total)
        )
        cpu_percent = self._sample_cpu_percent(now_ns)
        rss_bytes, memory_kind = self._rss_reader()

        record = {
            "record": "sample",
            "report_elapsed_s": round(
                (now_ns - (self._report_started_ns or now_ns)) / 1_000_000_000,
                3,
            ),
            "capture": _capture_snapshot(status),
            "rates": {
                "frames_per_s": round((frame_total - self._last_frame_total) / elapsed_s, 3),
                "messages_per_s": round(
                    (message_total - self._last_message_total) / elapsed_s,
                    3,
                ),
            },
            "process": {
                "cpu_percent_single_core": cpu_percent,
                "memory_bytes": rss_bytes,
                "memory_kind": memory_kind,
            },
            "poll_interval": self._window.poll_intervals.snapshot_ms(),
            "operations": {
                name: metric.snapshot_ms()
                for name, metric in self._window.operations.items()
            },
            "batches": {
                "frames": self._window.frame_batches.snapshot(),
                "messages": self._window.message_batches.snapshot(),
            },
        }
        self._write_record(record)
        self._last_sample_ns = now_ns
        self._last_frame_total = frame_total
        self._last_message_total = message_total
        self._window.reset()

    def _sample_cpu_percent(self, now_ns: int) -> float | None:
        current_cpu_ns = self._process_clock_ns()
        previous_wall_ns = self._last_process_wall_ns
        previous_cpu_ns = self._last_process_cpu_ns
        self._last_process_wall_ns = now_ns
        self._last_process_cpu_ns = current_cpu_ns
        if previous_wall_ns is None or previous_cpu_ns is None:
            return None
        wall_delta = now_ns - previous_wall_ns
        if wall_delta <= 0:
            return None
        return round(max(0.0, (current_cpu_ns - previous_cpu_ns) / wall_delta * 100.0), 3)

    def _finalize_report(self, reason: str) -> None:
        if self._handle is None:
            return
        self._emit_sample_if_due(self._clock_ns(), self._latest_status, force=True)
        self._write_record(
            {
                "record": "capture_finished",
                "reason": reason,
                "capture": _capture_snapshot(self._latest_status),
            }
        )
        self._last_sample_ns = None
        self.close()

    def _write_record(self, record: dict[str, object]) -> None:
        if self._handle is None:
            return
        payload = {
            "utc": self._utc_now().isoformat(),
            **record,
        }
        self._handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def maybe_instrument_live_controller(
    controller: LiveCaptureController,
    *,
    report_dir: Path,
) -> LiveCaptureController | InstrumentedLiveCaptureController:
    """Wrap the controller only when Stage H diagnostics are explicitly enabled."""

    if os.getenv("CRT_LIVE_PERF", "").strip().casefold() not in _TRUE_VALUES:
        return controller
    interval = _environment_interval()
    return InstrumentedLiveCaptureController(
        controller,
        report_dir=report_dir,
        sample_interval_s=interval,
    )


def _environment_interval() -> float:
    raw = os.getenv("CRT_LIVE_PERF_INTERVAL_S", "1.0").strip()
    try:
        value = float(raw)
    except ValueError:
        return 1.0
    return min(60.0, max(0.25, value))


def _capture_snapshot(status) -> dict[str, object] | None:
    if status is None:
        return None
    return {
        "state": _state_value(status),
        "elapsed_s": round(float(getattr(status, "elapsed_s", 0.0)), 3),
        "frame_count": int(getattr(status, "frame_count", 0)),
        "logical_message_count": int(getattr(status, "logical_message_count", 0)),
        "live_capacity": int(getattr(status, "live_capacity", 0)),
        "live_retained": int(getattr(status, "live_retained", 0)),
        "live_dropped_from_view": int(getattr(status, "live_dropped_from_view", 0)),
        "live_message_capacity": int(getattr(status, "live_message_capacity", 0)),
        "live_messages_retained": int(getattr(status, "live_messages_retained", 0)),
        "live_messages_dropped_from_view": int(
            getattr(status, "live_messages_dropped_from_view", 0)
        ),
    }


def _state_value(status) -> str:
    state = getattr(status, "state", "unknown")
    return str(getattr(state, "value", state)).casefold()


def _safe_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return normalized.strip("._-")[:80]


def _read_process_memory() -> tuple[int | None, str]:
    if sys.platform == "win32":
        return _read_windows_working_set()

    statm = Path("/proc/self/statm")
    if statm.exists():
        try:
            resident_pages = int(statm.read_text(encoding="ascii").split()[1])
            return resident_pages * os.sysconf("SC_PAGE_SIZE"), "current_rss"
        except (OSError, ValueError, IndexError):
            pass

    try:
        import resource

        maximum = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        multiplier = 1 if sys.platform == "darwin" else 1024
        return maximum * multiplier, "peak_rss"
    except (ImportError, OSError, ValueError):
        return None, "unavailable"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"cannot allocate unique performance report path: {path}")


def _read_windows_working_set() -> tuple[int | None, str]:
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        )
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        process = kernel32.GetCurrentProcess()
        success = psapi.GetProcessMemoryInfo(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
    except (AttributeError, OSError):
        return None, "unavailable"
    if not success:
        return None, "unavailable"
    return int(counters.WorkingSetSize), "current_working_set"
