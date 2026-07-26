from __future__ import annotations

from threading import Event
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from app.artifact_catalog import ArtifactIntegrityError
from app.extensions import ExtensionCancelled

from .comparison_visualization import (
    _ARTIFACT_TYPES,
    _SUPPORTED_SCHEMAS,
    ComparisonVisualizationDialog as _BaseComparisonVisualizationDialog,
)
from .comparison_visualization_model import (
    ComparisonDashboardData,
    build_dashboard_data,
)

_MAXIMUM_DASHBOARD_ARTIFACT_BYTES = 256 * 1024 * 1024


class _DashboardSignals(QObject):
    completed = Signal(int, object, object)
    failed = Signal(int, str)
    finished = Signal(int)


class _DashboardLoadTask(QRunnable):
    def __init__(
        self,
        generation: int,
        comparison_name: str,
        catalog,
        artifacts: tuple,
        cancel_event: Event,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.comparison_name = comparison_name
        self.catalog = catalog
        self.artifacts = artifacts
        self.cancel_event = cancel_event
        self.signals = _DashboardSignals()

    @Slot()
    def run(self) -> None:
        try:
            payloads: dict[str, dict[str, Any]] = {}
            errors: list[str] = []
            for artifact in self.artifacts:
                if self.cancel_event.is_set():
                    raise ExtensionCancelled("dashboard loading cancelled")
                try:
                    payload = self.catalog.read_json(
                        artifact,
                        maximum_bytes=_MAXIMUM_DASHBOARD_ARTIFACT_BYTES,
                    )
                except (ArtifactIntegrityError, OSError, ValueError) as exc:
                    errors.append(f"{artifact.artifact_type}: {exc}")
                    continue
                if not isinstance(payload, dict):
                    errors.append(
                        f"{artifact.artifact_type}: korzeń JSON nie jest obiektem"
                    )
                    continue
                schema = str(payload.get("schema") or "")
                if schema not in _SUPPORTED_SCHEMAS:
                    errors.append(
                        f"{artifact.artifact_type}: "
                        f"nieobsługiwany schemat {schema or 'brak'}"
                    )
                    continue
                payloads[schema] = payload
            if self.cancel_event.is_set():
                raise ExtensionCancelled("dashboard loading cancelled")
            data = build_dashboard_data(self.comparison_name, payloads)
            if not self.cancel_event.is_set():
                self.signals.completed.emit(self.generation, data, errors)
        except ExtensionCancelled:
            return
        except Exception as exc:  # pragma: no cover - surfaced through GUI
            if not self.cancel_event.is_set():
                self.signals.failed.emit(self.generation, str(exc))
        finally:
            self.signals.finished.emit(self.generation)


class ComparisonVisualizationDialog(_BaseComparisonVisualizationDialog):
    """Comparison dialog with cancellable background artifact loading."""

    def __init__(self, *args, **kwargs) -> None:
        self._dashboard_generation = 0
        self._dashboard_tasks: dict[int, _DashboardLoadTask] = {}
        self._close_when_idle = False
        super().__init__(*args, **kwargs)

    def _refresh_dashboard(self) -> None:
        if self.dashboard is None:
            return
        self._dashboard_generation += 1
        generation = self._dashboard_generation
        for task in self._dashboard_tasks.values():
            task.cancel_event.set()

        latest: dict[str, Any] = {}
        for artifact in self._artifacts:
            if artifact.artifact_type not in _ARTIFACT_TYPES:
                continue
            current = latest.get(artifact.artifact_type)
            if current is None or artifact.created_at_utc > current.created_at_utc:
                latest[artifact.artifact_type] = artifact

        if not latest:
            self.dashboard.clear()
            return

        cancel_event = Event()
        task = _DashboardLoadTask(
            generation,
            self.comparison_set.name,
            self.service.artifacts,
            tuple(latest.values()),
            cancel_event,
        )
        task.signals.completed.connect(self._dashboard_ready)
        task.signals.failed.connect(self._dashboard_failed)
        task.signals.finished.connect(self._dashboard_finished)
        self._dashboard_tasks[generation] = task
        QThreadPool.globalInstance().start(task)

    @Slot(int, object, object)
    def _dashboard_ready(
        self,
        generation: int,
        value: object,
        errors_value: object,
    ) -> None:
        if generation != self._dashboard_generation:
            return
        if not isinstance(value, ComparisonDashboardData):
            self._dashboard_failed(
                generation,
                "Nie udało się zbudować modelu dashboardu.",
            )
            return
        dashboard = self.dashboard
        if dashboard is None:
            return

        # Apply the already-built DTO only on the GUI thread.
        dashboard._data = value
        dashboard._update_cards()
        dashboard.heatmap.set_data(value.sessions, value.rows)
        dashboard.frequency_panel.set_rows(value.rows)
        dashboard._populate_table()

        errors = [
            str(item)
            for item in errors_value
            if str(item)
        ] if isinstance(errors_value, list) else []
        if errors:
            self.status_label.setText(
                "Nie udało się odczytać części artefaktów porównania: "
                + "; ".join(errors)
            )
        elif not value.artifact_schemas:
            dashboard.clear()

    @Slot(int, str)
    def _dashboard_failed(self, generation: int, error: str) -> None:
        if generation != self._dashboard_generation:
            return
        if self.dashboard is not None:
            self.dashboard.clear()
        self.status_label.setText(
            f"Nie udało się odświeżyć dashboardu porównania: {error}"
        )

    @Slot(int)
    def _dashboard_finished(self, generation: int) -> None:
        self._dashboard_tasks.pop(generation, None)

    def _cancel_dashboard_loads(self) -> None:
        self._dashboard_generation += 1
        for task in self._dashboard_tasks.values():
            task.cancel_event.set()

    def close_for_project_change(self) -> None:
        self._close_when_idle = True
        self._cancel_dashboard_loads()
        if self._task is not None:
            self._cancel_analysis()
            self.hide()
            return
        self.close()

    def _analysis_done(self, value: object) -> None:
        super()._analysis_done(value)
        self._close_if_requested()

    def _analysis_failed(self, error: str) -> None:
        super()._analysis_failed(error)
        self._close_if_requested()

    def _analysis_cancelled(self) -> None:
        super()._analysis_cancelled()
        self._close_if_requested()

    def _close_if_requested(self) -> None:
        if self._close_when_idle and self._task is None:
            self.close()

    def closeEvent(self, event) -> None:
        self._cancel_dashboard_loads()
        super().closeEvent(event)


__all__ = ["ComparisonVisualizationDialog"]
