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
        super()._build_menu()
        file_menu = next(
            (
                action.menu()
                for action in self.menuBar().actions()
                if action.menu() is not None
                and action.text().replace("&", "") == "Plik"
            ),
            None,
        )
        if file_menu is None:
            return
        actions = file_menu.actions()
        before = actions[2] if len(actions) >= 3 else None
        file_menu.insertAction(before, self.project_properties_action)

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
        try:
            project.update_manifest(
                name=dialog.project_name(),
                description=dialog.description(),
                default_bitrate=dialog.bitrate(),
                default_receive_mode=dialog.receive_mode(),
            )
        except Exception as exc:
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
                "nowe wartości domyślne dotyczą kolejnych sesji."
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
