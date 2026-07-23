from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from threading import Event, Lock
from types import MappingProxyType
from typing import Any

from app.domain import AnalysisInput
from app.models import CanFrame
from app.project import CrtProject, SessionRecord
from app.session_stream import SessionPagedReader


class ExtensionCancelled(RuntimeError):
    pass


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise ExtensionCancelled("extension execution was cancelled")


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    current: int
    total: int
    message: str = ""

    def __post_init__(self) -> None:
        if self.current < 0:
            raise ValueError("progress current cannot be negative")
        if self.total < 0:
            raise ValueError("progress total cannot be negative")
        if self.total and self.current > self.total:
            raise ValueError("progress current cannot exceed total")


class ProgressReporter:
    def __init__(self, callback: Callable[[ProgressUpdate], None] | None = None) -> None:
        self._callback = callback
        self._last = ProgressUpdate(0, 0, "")
        self._lock = Lock()

    @property
    def last(self) -> ProgressUpdate:
        with self._lock:
            return self._last

    def report(self, current: int, total: int, message: str = "") -> None:
        update = ProgressUpdate(current=current, total=total, message=message)
        with self._lock:
            if total == self._last.total and current < self._last.current:
                raise ValueError("progress cannot move backwards")
            self._last = update
        if self._callback is not None:
            self._callback(update)


class FrameQuery:
    """Read-only, bounded access to one immutable CRT session."""

    def __init__(
        self,
        reader: SessionPagedReader,
        cancellation: CancellationToken | None = None,
    ) -> None:
        self._reader = reader
        self._cancellation = cancellation or CancellationToken()

    @property
    def frame_count(self) -> int:
        return self._reader.frame_count

    def read(self, start: int, limit: int) -> tuple[CanFrame, ...]:
        self._cancellation.raise_if_cancelled()
        frames = tuple(self._reader.read_page(start, limit))
        self._cancellation.raise_if_cancelled()
        return frames

    def frame_at(self, source_row: int) -> CanFrame:
        frames = self.read(source_row, 1)
        if not frames:
            raise IndexError(f"frame source_row is outside the session: {source_row}")
        return frames[0]

    def iter_frames(
        self,
        *,
        start: int = 0,
        limit: int | None = None,
        cancellation_stride: int = 256,
    ) -> Iterator[CanFrame]:
        if cancellation_stride <= 0:
            raise ValueError("cancellation_stride must be greater than zero")
        self._cancellation.raise_if_cancelled()
        for index, frame in enumerate(self._reader.iter_frames(start=start, limit=limit)):
            if index % cancellation_stride == 0:
                self._cancellation.raise_if_cancelled()
            yield frame
        self._cancellation.raise_if_cancelled()


@dataclass(frozen=True, slots=True)
class SessionSource:
    id: str
    name: str
    source: str
    status: str
    frame_count: int
    marker_count: int
    duration_s: float
    sha256: str
    frames: FrameQuery


@dataclass(frozen=True, slots=True)
class ComparisonContext:
    """Immutable comparison-set snapshot supplied to a comparison provider."""

    id: str
    name: str
    session_ids: tuple[str, ...]
    base_session_id: str | None
    synchronization_mode: str
    parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("comparison context id cannot be empty")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("comparison context name cannot be empty")
        if len(self.session_ids) < 2:
            raise ValueError("comparison context requires at least two sessions")
        if len(set(self.session_ids)) != len(self.session_ids):
            raise ValueError("comparison context session_ids must be unique")
        if any(
            not isinstance(session_id, str) or not session_id.strip()
            for session_id in self.session_ids
        ):
            raise ValueError("comparison context session_id cannot be empty")
        if self.base_session_id is not None and self.base_session_id not in self.session_ids:
            raise ValueError("comparison context base_session_id must belong to session_ids")
        if (
            not isinstance(self.synchronization_mode, str)
            or not self.synchronization_mode.strip()
        ):
            raise ValueError("comparison context synchronization_mode cannot be empty")
        object.__setattr__(self, "session_ids", tuple(self.session_ids))
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


class ProjectContext:
    """Stable read-only project view exposed to extensions."""

    def __init__(
        self,
        project: CrtProject,
        cancellation: CancellationToken | None = None,
    ) -> None:
        self._project = project
        self._cancellation = cancellation or CancellationToken()

    @property
    def project_id(self) -> str:
        return self._project.manifest.id

    @property
    def project_name(self) -> str:
        return self._project.manifest.name

    @property
    def cancellation(self) -> CancellationToken:
        return self._cancellation

    def sessions(self) -> tuple[SessionSource, ...]:
        self._cancellation.raise_if_cancelled()
        return tuple(self._session_source(record) for record in self._project.list_sessions())

    def session(self, session_id: str) -> SessionSource:
        self._cancellation.raise_if_cancelled()
        record = next(
            (item for item in self._project.list_sessions() if item.id == session_id),
            None,
        )
        if record is None:
            raise KeyError(f"unknown session: {session_id}")
        return self._session_source(record)

    def _session_source(self, record: SessionRecord) -> SessionSource:
        reader = SessionPagedReader(self._project.absolute_path(record.relative_path))
        return SessionSource(
            id=record.id,
            name=record.name,
            source=record.source,
            status=record.status,
            frame_count=record.frame_count,
            marker_count=record.marker_count,
            duration_s=record.duration_s,
            sha256=record.sha256,
            frames=FrameQuery(reader, self._cancellation),
        )


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    project: ProjectContext
    analysis_run_id: str
    inputs: tuple[AnalysisInput, ...]
    cancellation: CancellationToken
    progress: ProgressReporter
    artifact_writer: object
    finding_writer: object
    comparison: ComparisonContext | None = None

    def __post_init__(self) -> None:
        if not self.analysis_run_id.strip():
            raise ValueError("analysis_run_id cannot be empty")
        if not self.inputs:
            raise ValueError("analysis context requires at least one input")
