from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDialog, QMessageBox

from app.project_catalog import load_project_profile, save_project_profile

from .project_properties_dialog import ProjectPropertiesDialog

if TYPE_CHECKING:
    from .main_window import MainWindow


class ProjectPropertiesController(QObject):
    """Edit project, vehicle and ECU metadata without moving the project folder."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window

    def edit(self) -> None:
        window = self._window
        project = window.project
        if project is None:
            QMessageBox.information(
                window,
                "CRT",
                "Najpierw otwórz lub utwórz projekt.",
            )
            return
        dialog = window.services.create_project_properties_dialog(window, project)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.apply_from_dialog(dialog)

    def apply_from_dialog(self, dialog: ProjectPropertiesDialog) -> None:
        window = self._window
        project = window.project
        if project is None:
            return
        catalog = window.project_catalog
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
            catalog.register_project(project.root)
        except Exception as exc:
            project.manifest = previous_manifest
            try:
                project._write_manifest()
                save_project_profile(project.root, previous_profile)
                catalog.register_project(project.root)
            except Exception as rollback_exc:
                window.append_output(
                    f"Nie udało się w pełni wycofać zmian właściwości projektu: {rollback_exc}"
                )
            QMessageBox.critical(
                window,
                "Nie można zapisać właściwości projektu",
                str(exc),
            )
            return

        window.refresh_project_identity()
        self._refresh_live_capture_defaults()
        window.append_output(
            f"Zaktualizowano właściwości projektu, pojazdu i ECU: {project.manifest.name}"
        )
        if window.has_active_capture():
            window.append_output(
                "Trwająca rejestracja zachowuje ustawienia wybrane przy jej uruchomieniu; "
                "pola domyślne widoku Live przygotowano dla kolejnej sesji."
            )

    def _refresh_live_capture_defaults(self) -> None:
        window = self._window
        project = window.project
        if project is None:
            return

        live_capture = window.navigator.widget("live-capture")
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
