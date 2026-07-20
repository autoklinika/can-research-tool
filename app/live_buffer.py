from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Iterable

from .models import CanFrame


@dataclass(frozen=True, slots=True)
class LiveFrameSnapshot:
    """Immutable view of the bounded live buffer.

    ``truncated`` means the requested cursor is older than the first frame still
    retained in the buffer. A GUI should then replace its current rows with the
    returned snapshot instead of appending them.
    """

    frames: tuple[CanFrame, ...]
    total_received: int
    capacity: int
    first_available_sequence: int | None
    last_available_sequence: int | None
    truncated: bool
    dropped_from_view: int


class LiveFrameBuffer:
    """Thread-safe bounded frame history for a responsive live view.

    The complete capture is written by ``SessionStreamWriter``. This buffer is
    deliberately lossy and keeps only the newest frames required by the GUI.
    """

    def __init__(self, capacity: int = 20_000) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        self._capacity = capacity
        self._frames: deque[CanFrame] = deque(maxlen=capacity)
        self._total_received = 0
        self._lock = RLock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()
            self._total_received = 0

    def append(self, frame: CanFrame) -> None:
        with self._lock:
            self._frames.append(frame)
            self._total_received += 1

    def append_many(self, frames: Iterable[CanFrame]) -> None:
        with self._lock:
            for frame in frames:
                self._frames.append(frame)
                self._total_received += 1

    def snapshot_since(self, after_sequence: int | None = None) -> LiveFrameSnapshot:
        """Return retained frames newer than ``after_sequence``.

        Passing ``None`` requests the complete retained window. The operation
        copies at most ``capacity`` frame references and never touches the full
        session file.
        """

        with self._lock:
            retained = tuple(self._frames)
            total_received = self._total_received

        if not retained:
            return LiveFrameSnapshot(
                frames=(),
                total_received=total_received,
                capacity=self._capacity,
                first_available_sequence=None,
                last_available_sequence=None,
                truncated=False,
                dropped_from_view=max(0, total_received),
            )

        first_sequence = retained[0].sequence
        last_sequence = retained[-1].sequence
        truncated = (
            after_sequence is not None and after_sequence < first_sequence - 1
        )

        if after_sequence is None or truncated:
            selected = retained
        elif after_sequence >= last_sequence:
            selected = ()
        else:
            selected = tuple(
                frame for frame in retained if frame.sequence > after_sequence
            )

        return LiveFrameSnapshot(
            frames=selected,
            total_received=total_received,
            capacity=self._capacity,
            first_available_sequence=first_sequence,
            last_available_sequence=last_sequence,
            truncated=truncated,
            dropped_from_view=max(0, total_received - len(retained)),
        )
