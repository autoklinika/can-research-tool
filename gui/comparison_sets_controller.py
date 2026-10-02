from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMessageBox

from app.comparison_evidence import ComparisonEvidenceLocation

from .comparison_evidence_navigation import ComparisonEvidenceCoordinator
from .comparison_sets_analysis_view import AnalysisEnabledComparisonSetsView
from .comparison_sets_view import ComparisonSetsView

if TYPE_CHECKING:
    from .main_window import MainWindow


_TAB_KEY = "comparison-sets"


class ComparisonSetsController(QObject):
    """Persistent comparison sets tab and navigation from analyses to raw evidence."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._coordinator: ComparisonEvidenceCoordinator | None = None

    def open(self, comparison_set_id: str = "") -> None:
        window = self._window
        project = window.project
        if project is None:
            QMessageBox.information(
                window,
                "CRT",
                "Najpierw otwórz lub utwórz projekt.",
            )
            return

        existing = window.navigator.widget(_TAB_KEY)
        if isinstance(existing, ComparisonSetsView):
            existing.refresh(comparison_set_id or None)
            window.navigator.activate(_TAB_KEY)
            return

        widget = window.services.create_comparison_sets_view(project)
        widget.changed.connect(window.explorer.refresh)
        widget.output_message.connect(window.append_output)
        if isinstance(widget, AnalysisEnabledComparisonSetsView):
            widget.evidence_open_requested.connect(self.open_evidence)
            widget.evidence_source_row_requested.connect(self.open_source_row)
        window.navigator.add_tab(_TAB_KEY, widget, "Zestawy porównawcze")
        if comparison_set_id:
            widget.select_comparison_set(comparison_set_id)

    def refresh(self) -> None:
        widget = self._window.navigator.widget(_TAB_KEY)
        if isinstance(widget, ComparisonSetsView):
            widget.refresh()

    def cancel_navigation(self, reason: str) -> None:
        if self._coordinator is not None:
            self._coordinator.cancel_all(reason)

    def open_evidence(
        self,
        session_id: str,
        message_key: str,
        requester: object | None = None,
    ) -> None:
        on_opened, on_failed = _requester_callbacks(requester)
        self._evidence_coordinator().open_evidence(
            session_id,
            message_key,
            on_opened=on_opened,
            on_failed=on_failed,
        )

    def open_source_row(
        self,
        session_id: str,
        source_row: int,
        message_key: str,
        requester: object | None = None,
    ) -> None:
        on_opened, on_failed = _requester_callbacks(requester)
        self._evidence_coordinator().open_source_row(
            session_id,
            int(source_row),
            message_key,
            on_opened=on_opened,
            on_failed=on_failed,
        )

    def _evidence_coordinator(self) -> ComparisonEvidenceCoordinator:
        if self._coordinator is None:
            self._coordinator = ComparisonEvidenceCoordinator(self._window)
        return self._coordinator


def _requester_callbacks(
    requester: object | None,
) -> tuple[
    Callable[[ComparisonEvidenceLocation], None] | None,
    Callable[[str], None] | None,
]:
    """Minimise the requesting analysis window on success, restore it on failure."""

    if requester is None:
        return None, None

    def opened(_location: ComparisonEvidenceLocation) -> None:
        callback = getattr(requester, "evidence_navigation_succeeded", None)
        if callable(callback):
            try:
                callback()
            except RuntimeError:
                pass
        minimize = getattr(requester, "showMinimized", None)
        if callable(minimize):
            try:
                minimize()
            except RuntimeError:
                pass

    def failed(error: str) -> None:
        callback = getattr(requester, "evidence_navigation_failed", None)
        if callable(callback):
            try:
                callback(error)
            except RuntimeError:
                pass
        show_normal = getattr(requester, "showNormal", None)
        raise_window = getattr(requester, "raise_", None)
        activate = getattr(requester, "activateWindow", None)
        for action in (show_normal, raise_window, activate):
            if callable(action):
                try:
                    action()
                except RuntimeError:
                    continue

    return opened, failed
