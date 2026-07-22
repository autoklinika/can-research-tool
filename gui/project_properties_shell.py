from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QMessageBox

from .project_properties_dialog import ProjectPropertiesDialog
from .search_enabled_shell import SearchEnabledMainWindow


class ProjectPropertiesMainWindow(SearchEnabledMainWindow):
    """Final CRT shell with safe editing of mutable project metadata."""

    def _build_actions(self) -> None:
        super()._build_actions()
        self.project_properties_action = QAction("Właściwości projektu…", self)
        self.project_properties_action.setObjectName("projectPropertiesAction")
        self.project_properties_action.setToolTip(
            "Edytuj nazwę, opis i domyślne ustawienia projektu bez zmiany folderu"
        )
        self.project_properties_action.setEnabled(False)
        self.project_properties_action.triggered.connect(self._edit_project)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.clear()

        file_menu = menu_bar.addMenu("Plik")
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addAction(self.project_properties_action)
        file_menu.addSeparator()
        file_menu.addAction(self.import_action)
        file_menu.addAction(self.save_log_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        view_menu = menu_bar.addMenu("Widok")
        view_menu.addAction(self.toggle_explorer_action)
        view_menu.addAction(self.toggle_inspector_action)
        view_menu.addAction(self.toggle_output_action)
        view_menu.addSeparator()
        view_menu.addAction(self.toggle_primary_toolbar_action)
        view_menu.addAction(self.reset_layout_action)

        capture_menu = menu_bar.addMenu("Capture")
        capture_menu.addAction(self.live_action)

        analysis_menu = menu_bar.addMenu("Analiza")
        analysis_menu.addAction(self.search_action)
        analysis_menu.addAction(self.compare_action)
        analysis_menu.addAction(self.signals_action)

        tools_menu = menu_bar.addMenu("Narzędzia")
        tools_menu.addAction(self.decoders_action)
        tools_menu.addAction(self.filters_action)
        tools_menu.addAction(self.session_markers_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.settings_action)

    def _set_project(self, project) -> None:
        super()._set_project(project)
        self.project_properties_action.setEnabled(self.project is not None)

    def _edit_project(self) -> None:
        project = self.project
        if project is None:
            QMessageBox.information(
                self,
                "CRT",
                "Najpierw otwórz lub utwórz projekt.",
            )
            return
        dialog = self.services.create_project_properties_dialog(self, project)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_project_properties_from_dialog(dialog)

    def _apply_project_properties_from_dialog(
        self,
        dialog: ProjectPropertiesDialog,
    ) -> None:
        project = self.project
        if project is None:
            return
        previous_manifest = project.manifest
        try:
            project.update_manifest(
                name=dialog.project_name(),
                description=dialog.description(),
                default_bitrate=dialog.bitrate(),
                default_receive_mode=dialog.receive_mode(),
            )
        except Exception as exc:
            project.manifest = previous_manifest
            QMessageBox.critical(
                self,
                "Nie można zapisać właściwości projektu",
                str(exc),
            )
            return

        self._refresh_project_identity()
        self._append_output(
            f"Zaktualizowano właściwości projektu: {project.manifest.name}"
        )
        if self._has_active_capture():
            self._append_output(
                "Trwająca rejestracja zachowuje ustawienia wybrane przy jej uruchomieniu; "
                "pola domyślne widoku Live przygotowano dla kolejnej sesji."
            )

    def _refresh_project_identity(self) -> None:
        project = self.project
        if project is None:
            return

        self.setWindowTitle(f"{project.manifest.name} — CAN Research Tool")
        self.project_status.setText(
            f"Projekt: {project.manifest.name} | {project.root}"
        )
        self.explorer.refresh()
        self._update_project_context()
        self._refresh_live_capture_defaults()

        overview = self.navigator.widget("project-overview")
        if overview is None:
            return

        previous_widget = self.tabs.currentWidget()
        previous_was_overview = previous_widget is overview
        self.navigator.close_widget(overview)
        self._open_overview()

        if (
            not previous_was_overview
            and previous_widget is not None
            and self.tabs.indexOf(previous_widget) >= 0
        ):
            self.tabs.setCurrentWidget(previous_widget)

        self.settings.setValue("project/lastPath", str(Path(project.root)))

    def _refresh_live_capture_defaults(self) -> None:
        project = self.project
        if project is None:
            return

        live_capture = self.navigator.widget("live-capture")
        if live_capture is None:
            return

        bitrate_combo = getattr(live_capture, "bitrate_combo", None)
        if bitrate_combo is not None:
            bitrate_index = bitrate_combo.findData(project.manifest.default_bitrate)
            if bitrate_index >= 0:
                bitrate_combo.setCurrentIndex(bitrate_index)

        mode_combo = getattr(live_capture, "mode_combo", None)
        if mode_combo is not None:
            mode_index = mode_combo.findData(project.manifest.default_receive_mode)
            if mode_index >= 0:
                mode_combo.setCurrentIndex(mode_index)
