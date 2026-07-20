from __future__ import annotations

from time import sleep

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.models import CanFrame
from app.static_frame_adapter import static_frame_record

from .live_filter_integration import (
    FILTER_WORKER_YIELD_EVERY,
    FILTER_WORKER_YIELD_SECONDS,
)


class StaticLiveFilterScanSignals(QObject):
    completed = Signal(int, object, int)
    failed = Signal(int, str)


class StaticLiveFilterScanTask(QRunnable):
    """Evaluate one immutable Live snapshot with the v2 static frame adapter."""

    def __init__(self, generation: int, frames: tuple[CanFrame, ...], filter_set) -> None:
        super().__init__()
        self.generation = generation
        self.frames = frames
        self.filter_set = filter_set
        self.signals = StaticLiveFilterScanSignals()

    @Slot()
    def run(self) -> None:
        try:
            accepted: list[CanFrame] = []
            evaluated_through = -1
            for index, frame in enumerate(self.frames, start=1):
                if self.filter_set.decide(static_frame_record(frame)).visible:
                    accepted.append(frame)
                evaluated_through = max(evaluated_through, frame.sequence)
                if index % FILTER_WORKER_YIELD_EVERY == 0:
                    sleep(FILTER_WORKER_YIELD_SECONDS)
            self.signals.completed.emit(
                self.generation,
                accepted,
                evaluated_through,
            )
        except Exception as exc:
            self.signals.failed.emit(self.generation, str(exc))


class StaticLiveIncrementalFilterSignals(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)


class StaticLiveIncrementalFilterTask(QRunnable):
    """Filter one bounded batch of newly captured frames with v2 fields."""

    def __init__(self, generation: int, frames: tuple[CanFrame, ...], filter_set) -> None:
        super().__init__()
        self.generation = generation
        self.frames = frames
        self.filter_set = filter_set
        self.signals = StaticLiveIncrementalFilterSignals()

    @Slot()
    def run(self) -> None:
        try:
            accepted: list[CanFrame] = []
            for index, frame in enumerate(self.frames, start=1):
                if self.filter_set.decide(static_frame_record(frame)).visible:
                    accepted.append(frame)
                if index % FILTER_WORKER_YIELD_EVERY == 0:
                    sleep(FILTER_WORKER_YIELD_SECONDS)
            self.signals.completed.emit(self.generation, accepted)
        except Exception as exc:
            self.signals.failed.emit(self.generation, str(exc))
