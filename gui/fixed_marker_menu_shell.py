from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QCloseEvent

from .live_capture import LiveCaptureWidget
from .restorable_dock_shell import RestorableDockEngineeringShellMainWindow


class FixedMarkerMenuMainWindow(RestorableDockEngineeringShellMainWindow):
    """Final shell with stable menus and explicit promotion of temporary Live logs."""

    def _build_actions(self) -> None:
        super()._build_actions()
        self.save_log_action = QAction("Zapisz log", self)
        self.save_log_action.setObjectName("savePendingLiveLogAction")
        self.save_log_action.setToolTip(
            "Przenieś zakończony log tymczasowy do trwałych sesji projektu"
        )
        self.save_log_action.setEnabled(False)
        self.save_log_action.triggered.connect(self._save_pending_live_log)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.clear()

        file_menu = menu_bar.addMenu("Plik")
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
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

    def _open_live_capture(self) -> None:
        super()._open_live_capture()
        widget = self._live_widget()
        if widget is None:
            self._sync_save_log_action()
            return
        if not bool(widget.property("crtSaveLogActionBound")):
            widget.status_text.connect(
                lambda _text: self._sync_save_log_action()
            )
            widget.project_changed.connect(self._sync_save_log_action)
            widget.setProperty("crtSaveLogActionBound", True)
        self._sync_save_log_action()

    def _live_widget(self) -> LiveCaptureWidget | None:
        navigator = getattr(self, "navigator", None)
        if navigator is None:
            return None
        widget = navigator.widget("live-capture")
        return widget if isinstance(widget, LiveCaptureWidget) else None

    @staticmethod
    def _live_save_integration(widget: LiveCaptureWidget | None):
        if widget is None:
            return None
        return getattr(widget, "_live_save_integration", None)

    def _sync_save_log_action(self) -> None:
        widget = self._live_widget()
        integration = self._live_save_integration(widget)
        enabled = bool(
            widget is not None
            and not widget.is_capturing
            and integration is not None
            and getattr(integration, "has_unsaved_log", False)
        )
        self.save_log_action.setEnabled(enabled)

    def _save_pending_live_log(self) -> None:
        widget = self._live_widget()
        integration = self._live_save_integration(widget)
        if integration is None:
            self._sync_save_log_action()
            return
        integration.save_pending_log()
        self.explorer.refresh()
        self._sync_save_log_action()

    def _confirm_unsaved_live_log(self, reason: str) -> bool:
        widget = self._live_widget()
        integration = self._live_save_integration(widget)
        if integration is None or not getattr(integration, "has_unsaved_log", False):
            return True
        accepted = bool(integration.confirm_pending_log(reason=reason))
        self.explorer.refresh()
        self._sync_save_log_action()
        return accepted

    def _close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if isinstance(widget, LiveCaptureWidget) and not widget.is_capturing:
            integration = self._live_save_integration(widget)
            if (
                integration is not None
                and getattr(integration, "has_unsaved_log", False)
                and not self._confirm_unsaved_live_log("close_tab")
            ):
                return
        super()._close_tab(index)
        self._sync_save_log_action()

    def _set_project(self, project) -> None:
        current = getattr(self, "project", None)
        changing = bool(
            current is not None
            and Path(current.root).resolve() != Path(project.root).resolve()
        )
        if changing and not self._confirm_unsaved_live_log("project_change"):
            return
        super()._set_project(project)
        self._sync_save_log_action()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._has_active_capture() and not self._confirm_unsaved_live_log("close"):
            event.ignore()
            return
        super().closeEvent(event)
