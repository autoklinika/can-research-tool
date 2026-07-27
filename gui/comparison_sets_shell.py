from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QMessageBox

from app.comparison_evidence import ComparisonEvidenceLocation
from app.project import CrtProject

from .comparison_evidence_navigation import ComparisonEvidenceCoordinator
from .comparison_sets_analysis_view import AnalysisEnabledComparisonSetsView
from .comparison_sets_view import ComparisonSetsView
from .project_properties_shell import ProjectPropertiesMainWindow


class ComparisonSetsMainWindow(ProjectPropertiesMainWindow):
    """CRT shell with persistent comparison sets and passive comparison analyses."""

    def _build_actions(self) -> None:
        super()._build_actions()
        try:
            self.compare_action.triggered.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.compare_action.setToolTip(
            "Twórz trwałe zestawy sesji i uruchamiaj pasywne analizy porównawcze"
        )
        self.compare_action.triggered.connect(
            lambda _checked=False: self._open_comparison_sets()
        )

    def _build_docks(self) -> None:
        super()._build_docks()
        self.explorer.open_comparison_sets.connect(self._open_comparison_sets)

    def _set_project(self, project: CrtProject) -> None:
        coordinator = getattr(self, "_comparison_evidence_coordinator", None)
        if isinstance(coordinator, ComparisonEvidenceCoordinator):
            coordinator.cancel_all(
                "Aktywny projekt został zmieniony podczas nawigacji do dowodu."
            )
        super()._set_project(project)

    def _open_comparison_sets(self, comparison_set_id: str = "") -> None:
        project = self.project
        if project is None:
            QMessageBox.information(
                self,
                "CRT",
                "Najpierw otwórz lub utwórz projekt.",
            )
            return

        key = "comparison-sets"
        existing = self.navigator.widget(key)
        if isinstance(existing, ComparisonSetsView):
            self._bind_comparison_evidence(existing)
            existing.refresh(comparison_set_id or None)
            self._activate_tab(key)
            return

        widget = self.services.create_comparison_sets_view(project)
        widget.changed.connect(self.explorer.refresh)
        widget.output_message.connect(self._append_output)
        self._bind_comparison_evidence(widget)
        self._add_tab(key, widget, "Zestawy porównawcze")
        if comparison_set_id:
            widget.select_comparison_set(comparison_set_id)

    def _bind_comparison_evidence(self, widget: ComparisonSetsView) -> None:
        if not isinstance(widget, AnalysisEnabledComparisonSetsView):
            return
        if bool(widget.property("comparisonEvidenceBound")):
            return
        widget.evidence_open_requested.connect(self._open_comparison_evidence)
        widget.evidence_source_row_requested.connect(
            self._open_comparison_source_row
        )
        widget.setProperty("comparisonEvidenceBound", True)

    def _open_comparison_evidence(
        self,
        session_id: str,
        message_key: str,
        requester: object | None = None,
    ) -> None:
        coordinator = self._evidence_coordinator()
        on_opened, on_failed = self._evidence_callbacks(requester)
        coordinator.open_evidence(
            session_id,
            message_key,
            on_opened=on_opened,
            on_failed=on_failed,
        )

    def _open_comparison_source_row(
        self,
        session_id: str,
        source_row: int,
        message_key: str,
        requester: object | None = None,
    ) -> None:
        coordinator = self._evidence_coordinator()
        on_opened, on_failed = self._evidence_callbacks(requester)
        coordinator.open_source_row(
            session_id,
            int(source_row),
            message_key,
            on_opened=on_opened,
            on_failed=on_failed,
        )

    def _evidence_coordinator(self) -> ComparisonEvidenceCoordinator:
        coordinator = getattr(self, "_comparison_evidence_coordinator", None)
        if not isinstance(coordinator, ComparisonEvidenceCoordinator):
            coordinator = ComparisonEvidenceCoordinator(self)
            self._comparison_evidence_coordinator = coordinator
        return coordinator

    def _evidence_callbacks(
        self,
        requester: object | None,
    ) -> tuple[
        Callable[[ComparisonEvidenceLocation], None] | None,
        Callable[[str], None] | None,
    ]:
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

    def _import_completed(self, source: str, target: str) -> None:
        super()._import_completed(source, target)
        widget = self.navigator.widget("comparison-sets")
        if isinstance(widget, ComparisonSetsView):
            widget.refresh()
