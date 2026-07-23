from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QMessageBox

from app.filters import FilterCompiler, ProjectFilterRepository

from .filter_manager import FilterManagerWidget
from .filter_shortcut_support import check_filter_shortcuts
from .main_window import MainWindow
from .window_fullscreen import enable_full_screen


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


class WindowedFilterMainWindow(MainWindow):
    """Main CRT window with a non-modal filter editor and preset shortcuts."""

    def __init__(self, services) -> None:
        self._filter_window: FilterManagerWindow | None = None
        self._preset_shortcuts: list[QShortcut] = []
        self._shortcut_issue_signature: tuple[str, ...] = ()
        super().__init__(services)

    def _build_actions(self) -> None:
        super()._build_actions()
        self.filters_action.setShortcut("Ctrl+D")
        self.filters_action.setShortcutContext(Qt.ApplicationShortcut)
        self.filters_action.setToolTip("Otwórz globalne filtry w osobnym oknie (Ctrl+D)")

    def _open_filters(self) -> None:
        if self.project is None:
            QMessageBox.information(
                self,
                "CRT",
                "Najpierw otwórz lub utwórz projekt.",
            )
            return

        project_root = Path(self.project.root)
        window = self._filter_window
        if window is not None and window.project_root == project_root:
            if window.isMinimized():
                window.showNormal()
            else:
                window.show()
            window.raise_()
            window.activateWindow()
            return

        if not self._dispose_filter_window():
            return
        manager = self.services.create_filter_manager(self.project)
        manager.output_message.connect(self._append_output)
        manager.changed.connect(self.explorer.refresh)
        manager.changed.connect(self._reload_filter_shortcuts)
        window = FilterManagerWindow(
            manager,
            project_name=self.project.manifest.name,
            project_root=project_root,
            parent=self,
        )
        self._filter_window = window
        window.show()
        window.raise_()
        window.activateWindow()

    def _set_project(self, project) -> None:
        if self._has_active_capture():
            super()._set_project(project)
            return

        previous = self.project
        changing_project = (
            previous is not None
            and Path(previous.root).resolve() != Path(project.root).resolve()
        )
        if changing_project and not self._dispose_filter_window():
            return

        super()._set_project(project)
        if self.project is not previous:
            self._reload_filter_shortcuts()

    def _dispose_filter_window(self) -> bool:
        window = self._filter_window
        if window is None:
            return True
        if not window.close():
            return False
        self._filter_window = None
        window.deleteLater()
        return True

    def _clear_filter_shortcuts(self) -> None:
        for shortcut in self._preset_shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._preset_shortcuts.clear()

    def _reload_filter_shortcuts(self) -> None:
        self._clear_filter_shortcuts()
        if self.project is None:
            return

        repository = ProjectFilterRepository(self.project.database_path)
        presets = repository.list_presets()
        check = check_filter_shortcuts(
            presets,
            project=self.project,
            action_root=self,
        )
        signature = check.messages
        if signature != self._shortcut_issue_signature:
            self._shortcut_issue_signature = signature
            for message in signature:
                self._append_output(f"Skrót filtra pominięty: {message}")

        for preset in presets:
            canonical = check.canonical_by_id.get(preset.id)
            if not canonical or preset.id in check.errors_by_id:
                continue
            shortcut = QShortcut(
                QKeySequence.fromString(canonical, QKeySequence.PortableText),
                self,
            )
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(
                lambda preset_id=preset.id: self._toggle_filter_preset(preset_id)
            )
            self._preset_shortcuts.append(shortcut)

    def _toggle_filter_preset(self, preset_id: str) -> None:
        if self.project is None:
            return

        window = self._filter_window
        if window is not None and window.has_pending_changes:
            self._append_output(
                "Nie przełączono presetu skrótem: najpierw zastosuj albo odrzuć zmiany w edytorze filtrów."
            )
            window.raise_()
            window.activateWindow()
            return

        repository = ProjectFilterRepository(self.project.database_path)
        presets = repository.list_presets()
        selected = next((preset for preset in presets if preset.id == preset_id), None)
        if selected is None:
            self._reload_filter_shortcuts()
            return

        target_enabled = not selected.enabled
        if target_enabled:
            issues = FilterCompiler().validate(selected)
            if issues:
                message = (
                    f"Nie można aktywować filtra „{selected.name}” skrótem: "
                    f"{issues[0].path}: {issues[0].message}"
                )
                self._append_output(message)
                QMessageBox.warning(self, "Nieprawidłowy filtr", message)
                return

        selected.enabled = target_enabled
        check = check_filter_shortcuts(
            presets,
            project=self.project,
            action_root=self,
        )
        if check.messages:
            message = "\n".join(check.messages[:10])
            self._append_output(f"Nie przełączono presetu: {message}")
            QMessageBox.warning(self, "Konflikt skrótów filtrów", message)
            return

        try:
            repository.save_presets(presets)
        except Exception as exc:
            QMessageBox.critical(self, "Nie można przełączyć filtra", str(exc))
            return

        state = "WŁĄCZONY" if selected.enabled else "WYŁĄCZONY"
        self._append_output(
            f"Filtr „{selected.name}”: {state} (skrót {selected.shortcut})"
        )
        self.explorer.refresh()
        if window is not None and hasattr(window.manager, "reload_from_repository"):
            window.manager.reload_from_repository()
        self._reload_filter_shortcuts()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._has_active_capture():
            super().closeEvent(event)
            return
        if not self._dispose_filter_window():
            event.ignore()
            return
        super().closeEvent(event)
        if event.isAccepted():
            self._clear_filter_shortcuts()
