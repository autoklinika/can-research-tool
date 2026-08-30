from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from app.comparison_uds_explorer_source import (
    PreferredUdsLatencySource,
    load_preferred_uds_latency_source,
)
from app.comparison_uds_latency import UdsLatencyCancelled
from app.domain import ComparisonSet
from app.extensions import CancellationToken, ExtensionCancelled
from app.project import CrtProject

from .comparison_uds_transaction_explorer_view import (
    ComparisonUdsTransactionExplorerView,
)


class _PreferredSourceSignals(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)
    cancelled = Signal(int)
    finished = Signal(int)


class _PreferredSourceLoadTask(QRunnable):
    def __init__(
        self,
        generation: int,
        service,
        comparison_set: ComparisonSet,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.service = service
        self.comparison_set = comparison_set
        self.cancellation = CancellationToken()
        self.signals = _PreferredSourceSignals()

    def cancel(self) -> None:
        self.cancellation.cancel()

    @Slot()
    def run(self) -> None:
        try:
            selected = load_preferred_uds_latency_source(
                self.service,
                self.comparison_set,
                should_cancel=lambda: self.cancellation.is_cancelled,
            )
            self.cancellation.raise_if_cancelled()
        except (UdsLatencyCancelled, ExtensionCancelled):
            self.signals.cancelled.emit(self.generation)
        except Exception as exc:  # pragma: no cover - surfaced through GUI
            self.signals.failed.emit(self.generation, str(exc))
        else:
            self.signals.completed.emit(self.generation, selected)
        finally:
            self.signals.finished.emit(self.generation)


class PreferredSourceUdsTransactionExplorerView(
    ComparisonUdsTransactionExplorerView
):
    """Explorer that does not let a newer empty Stage 2C2 artifact hide data."""

    def __init__(
        self,
        project: CrtProject,
        comparison_set: ComparisonSet,
        parent=None,
    ) -> None:
        super().__init__(project, comparison_set, parent)

    @Slot()
    def load_latest(self) -> None:
        generation = self._next_generation()
        task = _PreferredSourceLoadTask(
            generation,
            self.service,
            self.comparison_set,
        )
        task.signals.completed.connect(self._preferred_source_completed)
        task.signals.failed.connect(self._task_failed)
        task.signals.cancelled.connect(self._task_cancelled)
        task.signals.finished.connect(self._task_finished)
        self._tasks[generation] = task
        self._set_running(True)
        self.status_label.setText(
            "Szukam najnowszego artefaktu Stage 2C2 z transakcjami…"
        )
        QThreadPool.globalInstance().start(task)

    @Slot(int, object)
    def _preferred_source_completed(
        self,
        generation: int,
        value: object,
    ) -> None:
        if generation != self._generation:
            return
        if not isinstance(value, PreferredUdsLatencySource):
            self._task_failed(
                generation,
                "Nieobsługiwany wynik wyboru artefaktu UDS.",
            )
            return
        if value.stored is None:
            super()._task_completed(generation, None)
            return

        stored = value.stored
        self.set_source_result(stored.result, stored.artifact.id)
        configuration = stored.result.configuration
        request_count = sum(
            session.request_count for session in stored.result.sessions
        )
        message = self.status_label.text()
        message += (
            " Wczytano bez ponownego skanowania surowych sesji. "
            f"Klucze: {configuration.request_message_key} → "
            f"{configuration.response_message_key}; "
            f"żądania: {request_count}."
        )
        if value.skipped_newer_empty_artifacts:
            count = value.skipped_newer_empty_artifacts
            message += (
                f" Pominięto {count} nowszy"
                + (" pusty artefakt." if count == 1 else "ch pustych artefaktów.")
            )
        elif value.evidence_count == 0:
            message += (
                " Żaden zgodny artefakt Stage 2C2 nie zawiera zachowanych "
                "transakcji; sprawdź klucze w karcie Latencja UDS."
            )
        self.status_label.setText(message)


__all__ = ["PreferredSourceUdsTransactionExplorerView"]
