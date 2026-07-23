from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QWidget

from .session_artifact_selector import CompactArtifactSessionViewWidget


class MinimalAnalysisChromeSessionViewWidget(CompactArtifactSessionViewWidget):
    """Keep analysis controls visible while hiding idle and single-result chrome."""

    def __init__(self, *args, **kwargs) -> None:
        self._minimal_chrome_ready = False
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
        super()._load_artifacts(preferred_artifact_id=preferred_artifact_id)
        if self._minimal_chrome_ready:
            self._sync_result_navigation()
            if self.analysis_status.text().startswith("Nie można odczytać"):
                self._set_activity_visible(progress=False, status=True)

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
        self._set_activity_visible(progress=False, status=False)

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
        available = (
            self._analysis_service is not None
            and self._session_record is not None
            and self.analysis_provider_combo.count() > 0
        )
        if available:
            self._set_activity_visible(progress=False, status=False)
        else:
            self._set_activity_visible(progress=False, status=True)

    def _set_activity_visible(self, *, progress: bool, status: bool) -> None:
        self.analysis_progress.setVisible(progress)
        self.analysis_status.setVisible(status)


__all__ = ["MinimalAnalysisChromeSessionViewWidget"]
