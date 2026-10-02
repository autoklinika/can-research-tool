from __future__ import annotations

from pathlib import Path

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QSettings, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QMessageBox

from app.filters import ProjectFilterRepository
from app.static_filter_engine import StaticFilterCompiler

from .filter_manager import FilterManagerWidget
from .filter_shortcut_support import check_filter_shortcuts
from .window_fullscreen import enable_full_screen

if TYPE_CHECKING:
    from .main_window import MainWindow


class FilterManagerWindow(QMainWindow):
    """Independent non-modal window hosting the transactional filter editor."""

    def __init__(
        self,
        manager: FilterManagerWidget,
        *,
        project_name: str,
        project_root: Path,
        parent: QMainWindow,
    ) -> None:
        super().__init__(parent, Qt.Window)
        self.manager = manager
        self.project_root = Path(project_root)
        self.setObjectName("globalFilterWindow")
        self.setWindowTitle(f"Filtry — {project_name}")
        self.setCentralWidget(manager)
        self.setMinimumSize(1050, 650)
        self.resize(1450, 820)
        self.full_screen_controller = enable_full_screen(
            self,
            action_object_name="filterManagerFullScreenAction",
        )
        self.full_screen_action = self.full_screen_controller.action

        geometry = QSettings().value("windows/filterManagerGeometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    @property
    def has_pending_changes(self) -> bool:
        return bool(getattr(self.manager, "_dirty", False))

    def flush_pending_changes(self) -> bool:
        """Compatibility hook that never persists the editor's working copy."""

        timer = getattr(self.manager, "autosave_timer", None)
        if timer is not None:
            timer.stop()
        return not self.has_pending_changes

    def _confirm_pending_changes(self) -> bool:
        if not self.has_pending_changes:
            return True

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Niezastosowane zmiany filtrów")
        dialog.setText("Edytor zawiera zmiany, które nie zostały zastosowane.")
        dialog.setInformativeText(
            "Zastosuj je do projektu, odrzuć kopię roboczą albo wróć do edycji."
        )
        apply_button = dialog.addButton(
            "Zastosuj zmiany",
            QMessageBox.ButtonRole.AcceptRole,
        )
        discard_button = dialog.addButton(
            "Odrzuć zmiany",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(
            "Wróć do edycji",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(apply_button)
        dialog.exec()

        clicked = dialog.clickedButton()
        if clicked is apply_button:
            return bool(self.manager._save())
        if clicked is discard_button:
            discard = getattr(self.manager, "_discard_changes", None)
            if callable(discard):
                discard()
            elif hasattr(self.manager, "reload_from_repository"):
                self.manager.reload_from_repository()
            return True
        if clicked is cancel_button:
            return False
        return False

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._confirm_pending_changes():
            event.ignore()
            return
        QSettings().setValue("windows/filterManagerGeometry", self.saveGeometry())
        super().closeEvent(event)


class FilterPresetController(QObject):
    """Own the non-modal filter editor window and global preset shortcuts."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._editor_window: FilterManagerWindow | None = None
        self._shortcuts: list[QShortcut] = []
        self._shortcut_issue_signature: tuple[str, ...] = ()

    @property
    def editor_window(self) -> FilterManagerWindow | None:
        return self._editor_window

    @property
    def shortcuts(self) -> tuple[QShortcut, ...]:
        return tuple(self._shortcuts)

    def open_editor(self) -> None:
        main = self._window
        project = main.project
        if project is None:
            QMessageBox.information(
                main,
                "CRT",
                "Najpierw otwórz lub utwórz projekt.",
            )
            return

        project_root = Path(project.root)
        window = self._editor_window
        if window is not None and window.project_root == project_root:
            if window.isMinimized():
                window.showNormal()
            else:
                window.show()
            window.raise_()
            window.activateWindow()
            return

        if not self.close_editor():
            return
        manager = main.services.create_filter_manager(project)
        manager.output_message.connect(main.append_output)
        manager.changed.connect(main.explorer.refresh)
        manager.changed.connect(self.reload_shortcuts)
        window = FilterManagerWindow(
            manager,
            project_name=project.manifest.name,
            project_root=project_root,
            parent=main,
        )
        self._editor_window = window
        window.show()
        window.raise_()
        window.activateWindow()

    def close_editor(self) -> bool:
        """Close the editor; return False when the user keeps pending edits."""

        window = self._editor_window
        if window is None:
            return True
        if not window.close():
            return False
        self._editor_window = None
        window.deleteLater()
        return True

    def clear_shortcuts(self) -> None:
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts.clear()

    def reload_shortcuts(self) -> None:
        self.clear_shortcuts()
        main = self._window
        project = main.project
        if project is None:
            return

        repository = ProjectFilterRepository(project.database_path)
        presets = repository.list_presets()
        check = check_filter_shortcuts(
            presets,
            project=project,
            action_root=main,
        )
        signature = check.messages
        if signature != self._shortcut_issue_signature:
            self._shortcut_issue_signature = signature
            for message in signature:
                main.append_output(f"Skrót filtra pominięty: {message}")

        for preset in presets:
            canonical = check.canonical_by_id.get(preset.id)
            if not canonical or preset.id in check.errors_by_id:
                continue
            shortcut = QShortcut(
                QKeySequence.fromString(canonical, QKeySequence.PortableText),
                main,
            )
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(
                lambda preset_id=preset.id: self.toggle_preset(preset_id)
            )
            self._shortcuts.append(shortcut)

    def toggle_preset(self, preset_id: str) -> None:
        main = self._window
        project = main.project
        if project is None:
            return

        window = self._editor_window
        if window is not None and window.has_pending_changes:
            main.append_output(
                "Nie przełączono presetu skrótem: najpierw zastosuj albo odrzuć zmiany w edytorze filtrów."
            )
            window.raise_()
            window.activateWindow()
            return

        repository = ProjectFilterRepository(project.database_path)
        presets = repository.list_presets()
        selected = next((preset for preset in presets if preset.id == preset_id), None)
        if selected is None:
            self.reload_shortcuts()
            return

        target_enabled = not selected.enabled
        if target_enabled:
            issues = StaticFilterCompiler().validate(selected)
            if issues:
                message = (
                    f"Nie można aktywować filtra „{selected.name}” skrótem: "
                    f"{issues[0].path}: {issues[0].message}"
                )
                main.append_output(message)
                QMessageBox.warning(main, "Nieprawidłowy filtr", message)
                return

        selected.enabled = target_enabled
        check = check_filter_shortcuts(
            presets,
            project=project,
            action_root=main,
        )
        if check.messages:
            message = "\n".join(check.messages[:10])
            main.append_output(f"Nie przełączono presetu: {message}")
            QMessageBox.warning(main, "Konflikt skrótów filtrów", message)
            return

        try:
            repository.save_presets(presets)
        except Exception as exc:
            QMessageBox.critical(main, "Nie można przełączyć filtra", str(exc))
            return

        state = "WŁĄCZONY" if selected.enabled else "WYŁĄCZONY"
        main.append_output(
            f"Filtr „{selected.name}”: {state} (skrót {selected.shortcut})"
        )
        main.explorer.refresh()
        if window is not None:
            window.manager.reload_from_repository()
        self.reload_shortcuts()
