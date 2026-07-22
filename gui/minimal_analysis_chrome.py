from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QWidget

from .session_artifact_selector import (
    CompactArtifactSessionViewWidget,
    _selector_text,
)


class MinimalAnalysisChromeSessionViewWidget(CompactArtifactSessionViewWidget):
    """Keep analysis controls visible while hiding idle and single-result chrome."""

    def __init__(self, *args, **kwargs) -> None:
        self._minimal_chrome_ready = False
        self._artifact_catalog_error = False
        self.artifact_selector_bar: QWidget | None = None
        super().__init__(*args, **kwargs)

        selector = self.artifact_selector
        self.artifact_selector_bar = selector.parentWidget() if selector is not None else None
        if self.artifact_summary_line is not None:
            self.artifact_summary_line.setVisible(False)

        self._minimal_chrome_ready = True
        self._sync_result_navigation()
        self._sync_idle_activity_state()

    def _load_artifacts(self, *, preferred_artifact_id: str = "") -> None:
        service = self._analysis_service
        record = self._session_record
        catalog_error = ""
        if service is None or record is None:
            self._analysis_artifacts = ()
        else:
            try:
                self._analysis_artifacts = service.list_artifacts(record.id)
            except Exception as exc:
                self._analysis_artifacts = ()
                catalog_error = f"Nie można odczytać katalogu artefaktów: {exc}"

        selector = self.artifact_selector
        self._artifact_catalog_error = bool(catalog_error)
        if catalog_error:
            self.analysis_status.setText(catalog_error)
        elif self.analysis_status.text().startswith("Nie można odczytać"):
            self.analysis_status.clear()

        if selector is None:
            return

        previous_id = str(selector.currentData() or "")
        target_id = preferred_artifact_id or previous_id
        selector.blockSignals(True)
        selector.clear()
        target_index = -1
        for index, artifact in enumerate(self._analysis_artifacts):
            selector.addItem(_selector_text(artifact), artifact.id)
            if artifact.id == target_id:
                target_index = index
        if not self._analysis_artifacts:
            selector.addItem("Brak artefaktów analizy", "")
        selector.setEnabled(bool(self._analysis_artifacts))
        if self._analysis_artifacts:
            selector.setCurrentIndex(target_index if target_index >= 0 else 0)
        else:
            selector.setCurrentIndex(0)
        selector.blockSignals(False)

        self.tabs.setTabText(self.analysis_tab_index, f"Analizy ({len(self._analysis_artifacts)})")
        if self._analysis_artifacts:
            self._show_artifact_details(selector.currentIndex())
        else:
            self._clear_statistics("Brak artefaktu statystyk dla tej sesji.")
            self.artifact_details.setPlainText("Brak artefaktów analizy dla tej sesji.")
            self._set_artifact_summary(None)

        if self._minimal_chrome_ready:
            self._sync_result_navigation()
            self._sync_idle_activity_state()

    @Slot()
    def _start_analysis(self) -> None:
        super()._start_analysis()
        if self._analysis_task is not None:
            self._set_activity_visible(progress=True, status=True)
        else:
            self._sync_idle_activity_state()

    @Slot(int, int, str)
    def _analysis_progress_changed(self, current: int, total: int, message: str) -> None:
        self._set_activity_visible(progress=True, status=True)
        super()._analysis_progress_changed(current, total, message)

    @Slot(object)
    def _analysis_completed(self, result: object) -> None:
        super()._analysis_completed(result)
        self._sync_result_navigation()
        self._sync_idle_activity_state()

    @Slot(str)
    def _analysis_failed(self, error: str) -> None:
        super()._analysis_failed(error)
        self._set_activity_visible(progress=True, status=True)

    @Slot()
    def _analysis_cancelled(self) -> None:
        super()._analysis_cancelled()
        self._set_activity_visible(progress=True, status=True)

    def _sync_result_navigation(self) -> None:
        bar = self.artifact_selector_bar
        selector = self.artifact_selector
        if self.artifact_summary_line is not None:
            self.artifact_summary_line.setVisible(False)
        if bar is None or selector is None:
            return
        multiple_results = len(self._analysis_artifacts) > 1
        bar.setVisible(multiple_results)
        selector.setVisible(multiple_results)

    def _sync_idle_activity_state(self) -> None:
        if self._artifact_catalog_error:
            self._set_unavailable_progress("Błąd odczytu")
            self._set_activity_visible(progress=True, status=True)
            return

        available = (
            self._analysis_service is not None
            and self._session_record is not None
            and self.analysis_provider_combo.count() > 0
        )
        if available:
            self._set_activity_visible(progress=False, status=False)
        else:
            self._set_unavailable_progress("Niedostępne")
            self._set_activity_visible(progress=True, status=True)

    def _set_unavailable_progress(self, text: str) -> None:
        self.analysis_progress.setRange(0, 100)
        self.analysis_progress.setValue(0)
        self.analysis_progress.setFormat(text)

    def _set_activity_visible(self, *, progress: bool, status: bool) -> None:
        self.analysis_progress.setVisible(progress)
        self.analysis_status.setVisible(status)


__all__ = ["MinimalAnalysisChromeSessionViewWidget"]
