from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from .comparison_analysis_service import (
    ComparisonAnalysisExecutionResult,
    ComparisonAnalysisService,
)
from .extensions import ExtensionRegistry
from .extensions.builtin import (
    register_builtin_comparison_extensions,
    register_builtin_extensions,
)
from .extensions.builtin.experiment_marker_correlation import (
    EXPERIMENT_MARKER_CORRELATION_PROVIDER_ID,
    ExperimentMarkerCorrelationProvider,
)
from .marker_stream import iter_markers, marker_path_for_session
from .markers import CaptureMarker
from .project import CrtProject, SessionRecord


@dataclass(frozen=True, slots=True)
class MarkerSelectorOption:
    selector: str
    preset_id: str
    name: str
    label: str
    event_count: int
    session_count: int
    areas: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "preset_id": self.preset_id,
            "name": self.name,
            "label": self.label,
        }


class ExperimentDiffService:
    """Application layer that resolves immutable marker snapshots for Experiment Diff."""

    def __init__(self, project: CrtProject) -> None:
        self.project = project
        registry = ExtensionRegistry(passive_only=True, ai_enabled=False)
        register_builtin_extensions(registry)
        register_builtin_comparison_extensions(registry)
        registry.register(ExperimentMarkerCorrelationProvider())
        self.analysis = ComparisonAnalysisService(project, registry=registry)

    def marker_options(self, comparison_set_id: str) -> tuple[MarkerSelectorOption, ...]:
        comparison = self.analysis.comparison_sets.get(comparison_set_id)
        grouped: dict[str, list[tuple[str, CaptureMarker]]] = defaultdict(list)
        for session_id in comparison.session_ids:
            for marker in self._markers_for_session(session_id):
                grouped[_selector_for_marker(marker)].append((session_id, marker))

        options: list[MarkerSelectorOption] = []
        for selector, rows in grouped.items():
            names = Counter(marker.name for _session_id, marker in rows if marker.name)
            name = sorted(names.items(), key=lambda item: (-item[1], item[0].casefold()))[0][0] if names else selector
            preset_ids = {marker.preset_id for _session_id, marker in rows if marker.preset_id}
            preset_id = next(iter(preset_ids)) if len(preset_ids) == 1 else ""
            areas = tuple(sorted({marker.area for _session_id, marker in rows if marker.area}, key=str.casefold))
            session_count = len({session_id for session_id, _marker in rows})
            label = f"{name} — {len(rows)} zdarzeń / {session_count} sesji"
            if areas:
                label += f" — {', '.join(areas)}"
            options.append(
                MarkerSelectorOption(
                    selector=selector,
                    preset_id=preset_id,
                    name=name,
                    label=label,
                    event_count=len(rows),
                    session_count=session_count,
                    areas=areas,
                )
            )
        options.sort(key=lambda item: (item.name.casefold(), item.selector))
        return tuple(options)

    def run(
        self,
        comparison_set_id: str,
        *,
        target_selector: str,
        control_selector: str | None = None,
        pre_window_ms: float = 250.0,
        post_window_ms: float = 500.0,
        maximum_ranked_candidates: int = 500,
        maximum_evidence_events_per_candidate: int = 32,
        cancellation=None,
        progress_callback=None,
    ) -> ComparisonAnalysisExecutionResult:
        options = {item.selector: item for item in self.marker_options(comparison_set_id)}
        target = options.get(target_selector)
        if target is None:
            raise ValueError(f"unknown target marker selector: {target_selector}")
        control = None
        if control_selector:
            control = options.get(control_selector)
            if control is None:
                raise ValueError(f"unknown control marker selector: {control_selector}")
            if control.selector == target.selector:
                raise ValueError("target and control marker selectors must be different")

        comparison = self.analysis.comparison_sets.get(comparison_set_id)
        marker_events: list[dict[str, Any]] = []
        for session_id in comparison.session_ids:
            for marker in self._markers_for_session(session_id):
                selector = _selector_for_marker(marker)
                group = "target" if selector == target.selector else "control" if control and selector == control.selector else ""
                if not group:
                    continue
                marker_events.append(
                    {
                        "group": group,
                        "session_id": session_id,
                        "marker_id": marker.id,
                        "timestamp_ns": marker.timestamp_ns,
                        "preset_id": marker.preset_id,
                        "name": marker.name,
                        "shortcut": marker.shortcut,
                        "color": marker.color,
                        "area": marker.area,
                        "source": marker.source,
                        "note": marker.note,
                    }
                )
        marker_events.sort(key=lambda item: (str(item["session_id"]), int(item["timestamp_ns"]), str(item["marker_id"])))

        return self.analysis.run(
            EXPERIMENT_MARKER_CORRELATION_PROVIDER_ID,
            comparison_set_id,
            parameters={
                "target_marker": target.payload(),
                "control_marker": None if control is None else control.payload(),
                "pre_window_ms": float(pre_window_ms),
                "post_window_ms": float(post_window_ms),
                "maximum_ranked_candidates": int(maximum_ranked_candidates),
                "maximum_evidence_events_per_candidate": int(maximum_evidence_events_per_candidate),
                "marker_events": marker_events,
            },
            cancellation=cancellation,
            progress_callback=progress_callback,
        )

    def list_artifacts(self, comparison_set_id: str):
        return tuple(
            artifact
            for artifact in self.analysis.list_artifacts(comparison_set_id)
            if artifact.artifact_type == "experiment_marker_correlation"
        )

    def _markers_for_session(self, session_id: str) -> tuple[CaptureMarker, ...]:
        record = _session_record(self.project, session_id)
        session_path = self.project.absolute_path(record.relative_path)
        sidecar = marker_path_for_session(session_path)
        if sidecar.is_file():
            markers = tuple(iter_markers(sidecar))
            if markers or record.marker_count == 0:
                return markers

        # Older projects may have the indexed marker rows even when the sidecar
        # is unavailable. This is read-only fallback; sidecar snapshots remain
        # preferred because imported CRT sessions preserve them verbatim.
        with self.project._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, timestamp_ns, preset_id, name, shortcut, color, area, source, note
                FROM session_markers
                WHERE session_id = ?
                ORDER BY timestamp_ns, id
                """,
                (session_id,),
            ).fetchall()
        return tuple(
            CaptureMarker(
                id=str(row[0]),
                timestamp_ns=int(row[1]),
                preset_id=str(row[2]),
                name=str(row[3]),
                shortcut=str(row[4]),
                color=str(row[5]),
                area=str(row[6]),
                source=str(row[7]),
                note=str(row[8]),
            )
            for row in rows
        )


def _selector_for_marker(marker: CaptureMarker) -> str:
    if marker.preset_id.strip():
        return f"preset:{marker.preset_id.strip()}"
    return f"name:{marker.name.strip().casefold()}"


def _session_record(project: CrtProject, session_id: str) -> SessionRecord:
    record = next((item for item in project.list_sessions() if item.id == session_id), None)
    if record is None:
        raise KeyError(f"unknown session: {session_id}")
    return record


__all__ = ["ExperimentDiffService", "MarkerSelectorOption"]
