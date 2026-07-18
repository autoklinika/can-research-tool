from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QMessageBox

from .filter_manager import FilterManagerWidget
from .main_window import MainWindow


class FilterManagerWindow(QMainWindow):
    """Independent non-modal window hosting the project filter editor."""

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

        geometry = QSettings().value("windows/filterManagerGeometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def flush_pending_changes(self) -> None:
        """Persist a pending autosave before the top-level window is hidden."""

        if self.manager.autosave_timer.isActive():
            self.manager.autosave_timer.stop()
        self.manager._autosave()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.flush_pending_changes()
        QSettings().setValue("windows/filterManagerGeometry", self.saveGeometry())
        super().closeEvent(event)


class WindowedFilterMainWindow(MainWindow):
    """Main CRT window with global filters outside the central tab workspace."""

    def __init__(self, services) -> None:
        self._filter_window: FilterManagerWindow | None = None
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

        self._dispose_filter_window()
        manager = self.services.create_filter_manager(self.project)
        manager.output_message.connect(self._append_output)
        manager.changed.connect(self.explorer.refresh)
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
        previous = self.project
        super()._set_project(project)
        if self.project is not previous:
            self._dispose_filter_window()

    def _dispose_filter_window(self) -> None:
        window = self._filter_window
        if window is None:
            return
        self._filter_window = None
        window.flush_pending_changes()
        window.close()
        window.deleteLater()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        super().closeEvent(event)
        if event.isAccepted():
            self._dispose_filter_window()
