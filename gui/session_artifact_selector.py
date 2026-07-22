from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.domain import Artifact

from .session_statistics_visual_summary import VisualSessionStatisticsViewWidget


class CompactArtifactSessionViewWidget(VisualSessionStatisticsViewWidget):
    """Stored-session analysis view with a compact artifact selector."""

    def __init__(self, *args, **kwargs) -> None:
        self._artifact_selector_ready = False
        self.artifact_selector: QComboBox | None = None
        self.artifact_summary_line: QLabel | None = None
        self.artifact_info_toggle: QToolButton | None = None
        super().__init__(*args, **kwargs)
        self._install_compact_artifact_workspace()
        self._artifact_selector_ready = True
        preferred = self._analysis_artifacts[0].id if self._analysis_artifacts else ""
        self._load_artifacts(preferred_artifact_id=preferred)

    def _install_compact_artifact_workspace(self) -> None:
        tabs = self.artifact_detail_tabs
        if tabs is None:
            raise RuntimeError("artifact detail tabs are not available")
        splitter = tabs.parentWidget()
        if not isinstance(splitter, QSplitter):
            raise RuntimeError("artifact workspace splitter was not found")
        analysis_page = splitter.parentWidget()
        root = analysis_page.layout() if analysis_page is not None else None
        if not isinstance(root, QVBoxLayout):
            raise RuntimeError("analysis workspace layout was not found")

        selector_bar = QWidget(analysis_page)
        selector_bar.setObjectName("sessionArtifactSelectorBar")
        selector_layout = QHBoxLayout(selector_bar)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(8)
        selector_layout.addWidget(QLabel("Wynik analizy:", selector_bar))

        selector = QComboBox(selector_bar)
        selector.setObjectName("sessionArtifactSelector")
        selector.setMinimumWidth(360)
        selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        selector.currentIndexChanged.connect(self._artifact_selector_changed)
        selector_layout.addWidget(selector)

        summary = QLabel("Brak artefaktów", selector_bar)
        summary.setObjectName("sessionArtifactSummaryLine")
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        summary.setWordWrap(False)
        selector_layout.addWidget(summary, 1)

        root.insertWidget(root.indexOf(splitter), selector_bar)
        self.artifact_selector = selector
        self.artifact_summary_line = summary

        old_table = self.artifact_table
        if old_table is not None:
            old_table.setParent(None)
            old_table.deleteLater()
        self.artifact_table = None
        splitter.setHandleWidth(0)
        splitter.setSizes((1,))

        visual_page = self.statistics_visual_page
        visual_layout = visual_page.layout() if visual_page is not None else None
        if not isinstance(visual_layout, QVBoxLayout):
            raise RuntimeError("visual summary layout was not found")
        old_title = visual_page.findChild(QLabel, "sessionStatisticsTechnicalTitle")
        details_index = visual_layout.indexOf(self.artifact_details)
        if old_title is not None:
            old_title_index = visual_layout.indexOf(old_title)
            visual_layout.removeWidget(old_title)
            old_title.deleteLater()
            if old_title_index >= 0:
                details_index = old_title_index

        toggle = QToolButton(visual_page)
        toggle.setObjectName("sessionArtifactInfoToggle")
        toggle.setText("Informacje o artefakcie")
        toggle.setCheckable(True)
        toggle.setChecked(False)
        toggle.setArrowType(Qt.ArrowType.RightArrow)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.toggled.connect(self._artifact_info_toggled)
        visual_layout.insertWidget(max(0, details_index), toggle)
        self.artifact_info_toggle = toggle

        self.artifact_details.setObjectName("sessionArtifactTechnicalDetails")
        self.artifact_details.setMaximumHeight(210)
        self.artifact_details.setVisible(False)

    def _load_artifacts(self, *, preferred_artifact_id: str = "") -> None:
        if not self._artifact_selector_ready:
            super()._load_artifacts(preferred_artifact_id=preferred_artifact_id)
            return

        service = self._analysis_service
        record = self._session_record
        if service is None or record is None:
            self._analysis_artifacts = ()
        else:
            try:
                self._analysis_artifacts = service.list_artifacts(record.id)
            except Exception as exc:
                self._analysis_artifacts = ()
                self.analysis_status.setText(f"Nie można odczytać katalogu artefaktów: {exc}")

        selector = self.artifact_selector
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

    def _show_artifact_details(self, row: int) -> None:
        super()._show_artifact_details(row)
        if not self._artifact_selector_ready:
            return
        if not 0 <= row < len(self._analysis_artifacts):
            self.artifact_details.setPlainText("Brak artefaktów analizy dla tej sesji.")
            self._set_artifact_summary(None)
            return
        artifact = self._analysis_artifacts[row]
        self.artifact_details.setPlainText(_format_artifact_information(artifact))
        self._set_artifact_summary(artifact)
        selector = self.artifact_selector
        if selector is not None and selector.currentIndex() != row:
            selector.blockSignals(True)
            selector.setCurrentIndex(row)
            selector.blockSignals(False)

    @Slot(int)
    def _artifact_selector_changed(self, index: int) -> None:
        if not self._artifact_selector_ready:
            return
        self._show_artifact_details(index)

    @Slot(bool)
    def _artifact_info_toggled(self, expanded: bool) -> None:
        toggle = self.artifact_info_toggle
        if toggle is not None:
            toggle.setArrowType(
                Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
            )
        self.artifact_details.setVisible(expanded)

    def _set_artifact_summary(self, artifact: Artifact | None) -> None:
        label = self.artifact_summary_line
        toggle = self.artifact_info_toggle
        if label is None:
            return
        if artifact is None:
            label.setText("Brak wyników analizy")
            label.setToolTip("")
            if toggle is not None:
                toggle.setEnabled(False)
                toggle.setChecked(False)
            return
        label.setText(
            f"{_artifact_name(artifact)} · {_display_timestamp(artifact.created_at_utc)} · "
            f"wersja {artifact.provider_version}"
        )
        label.setToolTip(
            f"Provider: {artifact.provider_id}\nAlgorytm: {artifact.algorithm_version}\n"
            f"Schemat: {artifact.schema_version}\nPlik: {artifact.relative_path or '—'}"
        )
        if toggle is not None:
            toggle.setEnabled(True)


def _artifact_name(artifact: Artifact) -> str:
    names = {
        "session_statistics": "Statystyki sesji",
    }
    return names.get(artifact.artifact_type, artifact.artifact_type.replace("_", " ").title())


def _selector_text(artifact: Artifact) -> str:
    return (
        f"{_artifact_name(artifact)} — {_display_timestamp(artifact.created_at_utc)} — "
        f"v{artifact.provider_version}"
    )


def _display_timestamp(value: str) -> str:
    return value.replace("T", " ").replace("+00:00", "Z") if value else "—"


def _format_artifact_information(artifact: Artifact) -> str:
    sources = ", ".join(
        f"{source.session_id}:{source.source_kind}" for source in artifact.sources
    )
    return "\n".join(
        (
            "INFORMACJE O ARTEFAKCIE",
            "",
            f"ID: {artifact.id}",
            f"Typ: {artifact.artifact_type}",
            f"Provider: {artifact.provider_id}",
            f"Wersja providera: {artifact.provider_version}",
            f"Algorytm: {artifact.algorithm_version}",
            f"Schemat: {artifact.schema_version}",
            f"Utworzono: {_display_timestamp(artifact.created_at_utc)}",
            f"Plik: {artifact.relative_path or '—'}",
            f"SHA-256: {artifact.sha256 or '—'}",
            f"Źródła: {sources or '—'}",
        )
    )


__all__ = ["CompactArtifactSessionViewWidget"]
