from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .domain import Artifact
from .extensions import CancellationToken, ProgressUpdate
from .extensions.builtin import SIGNAL_PLOT_SERIES_ARTIFACT_SCHEMA_VERSION, SIGNAL_PLOT_SERIES_PROVIDER_ID
from .project import CrtProject
from .session_analysis_service import AnalysisExecutionResult, SessionAnalysisService


_MAXIMUM_ARTIFACT_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CursorDelta:
    delta_time_ns: int
    delta_value: float

    @property
    def delta_time_s(self) -> float:
        return self.delta_time_ns / 1_000_000_000.0


class SignalPlotService:
    """Application service for complete deterministic signal plot series."""

    def __init__(self, project: CrtProject) -> None:
        self.project = project
        self.analysis = SessionAnalysisService(project)
        self.artifacts = self.analysis.artifacts

    def run(
        self,
        session_id: str,
        *,
        parameters: Mapping[str, Any],
        cancellation: CancellationToken | None = None,
        progress_callback: Callable[[ProgressUpdate], None] | None = None,
    ) -> AnalysisExecutionResult:
        return self.analysis.run(
            SIGNAL_PLOT_SERIES_PROVIDER_ID,
            session_id,
            parameters=parameters,
            cancellation=cancellation,
            progress_callback=progress_callback,
        )

    def list_artifacts(self, session_id: str) -> tuple[Artifact, ...]:
        return tuple(
            artifact
            for artifact in self.analysis.list_artifacts(session_id)
            if artifact.artifact_type == "signal_plot_series"
            and artifact.schema_version == SIGNAL_PLOT_SERIES_ARTIFACT_SCHEMA_VERSION
        )

    def read_series(self, artifact: Artifact) -> Mapping[str, Any]:
        if artifact.artifact_type != "signal_plot_series":
            raise ValueError("artifact is not signal_plot_series")
        if artifact.schema_version != SIGNAL_PLOT_SERIES_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported signal_plot_series schema: {artifact.schema_version}"
            )
        payload = self.artifacts.read_json(
            artifact,
            maximum_bytes=_MAXIMUM_ARTIFACT_BYTES,
        )
        if payload.get("schema") != "crt.signal_plot_series":
            raise ValueError("unexpected signal plot artifact schema")
        contract = _mapping(payload.get("series_contract"))
        if contract.get("complete") is not True or contract.get("sampling") != "none":
            raise ValueError("signal plot artifact is not a complete unsampled series")
        points = payload.get("points")
        if not isinstance(points, list):
            raise ValueError("signal plot artifact has no point list")
        return payload


def nearest_point_index(
    points: Sequence[Mapping[str, Any]],
    timestamp_ns: int,
) -> int:
    """Return the nearest exact point by timestamp from a sorted full series."""

    if not points:
        raise ValueError("point series is empty")
    timestamps = [int(point["timestamp_ns"]) for point in points]
    target = int(timestamp_ns)
    index = bisect_left(timestamps, target)
    if index <= 0:
        return 0
    if index >= len(timestamps):
        return len(timestamps) - 1
    before = timestamps[index - 1]
    after = timestamps[index]
    return index - 1 if target - before <= after - target else index


def cursor_delta(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> CursorDelta:
    return CursorDelta(
        delta_time_ns=int(second["timestamp_ns"]) - int(first["timestamp_ns"]),
        delta_value=float(second["value"]) - float(first["value"]),
    )


def decimate_for_render(
    points: Sequence[Mapping[str, Any]],
    maximum_points: int,
) -> tuple[Mapping[str, Any], ...]:
    """Reduce only the visual polyline while preserving bucket extrema and endpoints."""

    limit = int(maximum_points)
    if limit < 4:
        raise ValueError("maximum_points must be at least 4")
    count = len(points)
    if count <= limit:
        return tuple(points)
    if not points:
        return ()

    # Reserve first/last and use min/max values from interior buckets. Rendering is
    # allowed to decimate, but cursor selection always uses the original full series.
    interior = points[1:-1]
    bucket_count = max(1, (limit - 2) // 2)
    result: list[Mapping[str, Any]] = [points[0]]
    for bucket in range(bucket_count):
        start = (bucket * len(interior)) // bucket_count
        end = ((bucket + 1) * len(interior)) // bucket_count
        chunk = interior[start:end]
        if not chunk:
            continue
        low = min(chunk, key=lambda item: float(item["value"]))
        high = max(chunk, key=lambda item: float(item["value"]))
        if int(low["timestamp_ns"]) <= int(high["timestamp_ns"]):
            result.append(low)
            if high is not low:
                result.append(high)
        else:
            result.append(high)
            if high is not low:
                result.append(low)
    result.append(points[-1])
    if len(result) > limit:
        # Deterministic final thinning only of the rendering list; first/last stay exact.
        keep = [result[0]]
        span = len(result) - 2
        slots = limit - 2
        for index in range(slots):
            source_index = 1 + (index * span) // slots
            keep.append(result[source_index])
        keep.append(result[-1])
        result = keep
    return tuple(result)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "CursorDelta",
    "SignalPlotService",
    "cursor_delta",
    "decimate_for_render",
    "nearest_point_index",
]
