from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QMessageBox

from app.project import CrtProject
from app.project_catalog import ProjectCatalog, load_project_profile, save_project_profile

from .project_catalog_dialog import ProjectCatalogDialog
from .project_properties_dialog import ProjectPropertiesDialog
from .search_enabled_shell import SearchEnabledMainWindow


class ProjectPropertiesMainWindow(SearchEnabledMainWindow):
    """Final CRT shell with managed project catalog and editable metadata."""

    def __init__(self, services) -> None:
        self.project_catalog = ProjectCatalog()
        super().__init__(services)

    def _build_actions(self) -> None:
        super()._build_actions()
        try:
            self.open_project_action.triggered.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.open_project_action.setText("Otwórz projekt CRT…")
        self.open_project_action.setToolTip(
            "Wybierz projekt z centralnego katalogu CAN Research Tool"
        )
        self.open_project_action.triggered.connect(self._open_project_catalog)

        self.project_properties_action = QAction("Właściwości projektu…", self)
        self.project_properties_action.setObjectName("projectPropertiesAction")
        self.project_properties_action.setToolTip(
            "Edytuj dane projektu, pojazdu i sterownika ECU bez zmiany folderu"
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

    def _open_project_catalog(self) -> None:
        try:
            self.project_catalog.refresh_availability()
            dialog = ProjectCatalogDialog(self.project_catalog, self)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Nie można otworzyć katalogu projektów",
                str(exc),
            )
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        path = dialog.selected_project_path()
        if not path:
            return
        try:
            self._open_project_path(Path(path))
        except Exception as exc:
            self.project_catalog.refresh_availability()
            QMessageBox.critical(
                self,
                "Nie można otworzyć projektu",
                str(exc),
            )

    def _create_project_from_dialog(self, dialog) -> None:
        try:
            project = CrtProject.create(
                dialog.project_root(),
                name=dialog.project_name(),
                description=dialog.description(),
                default_bitrate=dialog.bitrate(),
                default_receive_mode=dialog.receive_mode(),
            )
            self.project_catalog.register_project(
                project.root,
                profile=dialog.profile(),
                opened=True,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Nie można utworzyć projektu", str(exc))
            return
        self._set_project(project)
        self._append_output(f"Utworzono projekt i dodano do katalogu CRT: {project.root}")

    def _open_project_path(self, path: Path) -> None:
        project = CrtProject.open(path)
        self.project_catalog.register_project(project.root, opened=True)
        self._set_project(project)
        self._append_output(f"Otwarto projekt z katalogu CRT: {path}")

    def _set_project(self, project) -> None:
        super()._set_project(project)
        accepted = self.project is project
        self.project_properties_action.setEnabled(self.project is not None)
        if accepted:
            try:
                entry = self.project_catalog.register_project(project.root, opened=True)
                self.project_catalog.mark_opened(entry.project_id)
            except Exception as exc:
                self._append_output(f"Nie udało się zaktualizować katalogu projektów: {exc}")

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
        previous_profile = load_project_profile(project.root)
        try:
            project.update_manifest(
                name=dialog.project_name(),
                description=dialog.description(),
                default_bitrate=dialog.bitrate(),
                default_receive_mode=dialog.receive_mode(),
            )
            save_project_profile(project.root, dialog.profile())
            self.project_catalog.register_project(project.root)
        except Exception as exc:
            project.manifest = previous_manifest
            try:
                project._write_manifest()
                save_project_profile(project.root, previous_profile)
                self.project_catalog.register_project(project.root)
            except Exception as rollback_exc:
                self._append_output(
                    f"Nie udało się w pełni wycofać zmian właściwości projektu: {rollback_exc}"
                )
            QMessageBox.critical(
                self,
                "Nie można zapisać właściwości projektu",
                str(exc),
            )
            return

        self._refresh_project_identity()
        self._append_output(
            f"Zaktualizowano właściwości projektu, pojazdu i ECU: {project.manifest.name}"
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
            default_bitrate = int(project.manifest.default_bitrate)
            bitrate_index = bitrate_combo.findData(default_bitrate)
            if bitrate_index < 0:
                bitrate_combo.addItem(
                    f"{default_bitrate:,}".replace(",", " "),
                    default_bitrate,
                )
                bitrate_index = bitrate_combo.findData(default_bitrate)
            bitrate_combo.setCurrentIndex(bitrate_index)

        mode_combo = getattr(live_capture, "mode_combo", None)
        if mode_combo is not None:
            mode_index = mode_combo.findData(project.manifest.default_receive_mode)
            if mode_index >= 0:
                mode_combo.setCurrentIndex(mode_index)
