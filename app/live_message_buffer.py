from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Iterable

from .logical_records import LogicalMessageRecord


@dataclass(frozen=True, slots=True)
class LiveMessageSnapshot:
    messages: tuple[LogicalMessageRecord, ...]
    total_received: int
    capacity: int
    first_available_sequence: int | None
    last_available_sequence: int | None
    truncated: bool
    dropped_from_view: int


class LiveMessageBuffer:
    """Thread-safe bounded history of reconstructed logical messages."""

    def __init__(self, capacity: int = 5_000) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        self._capacity = capacity
        self._messages: deque[LogicalMessageRecord] = deque(maxlen=capacity)
        self._total_received = 0
        self._lock = RLock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def append(self, message: LogicalMessageRecord) -> None:
        with self._lock:
            self._messages.append(message)
            self._total_received += 1

    def append_many(self, messages: Iterable[LogicalMessageRecord]) -> None:
        with self._lock:
            for message in messages:
                self._messages.append(message)
                self._total_received += 1

    def snapshot_since(self, after_sequence: int | None = None) -> LiveMessageSnapshot:
        with self._lock:
            retained = tuple(self._messages)
            total_received = self._total_received

        if not retained:
            return LiveMessageSnapshot(
                messages=(),
                total_received=total_received,
                capacity=self._capacity,
                first_available_sequence=None,
                last_available_sequence=None,
                truncated=False,
                dropped_from_view=max(0, total_received),
            )

        first_sequence = retained[0].sequence
        last_sequence = retained[-1].sequence
        truncated = after_sequence is not None and after_sequence < first_sequence - 1
        if after_sequence is None or truncated:
            selected = retained
        elif after_sequence >= last_sequence:
            selected = ()
        else:
            selected = tuple(
                message for message in retained if message.sequence > after_sequence
            )

        return LiveMessageSnapshot(
            messages=selected,
            total_received=total_received,
            capacity=self._capacity,
            first_available_sequence=first_sequence,
            last_available_sequence=last_sequence,
            truncated=truncated,
            dropped_from_view=max(0, total_received - len(retained)),
        )
