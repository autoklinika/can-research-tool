from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDockWidget, QTableView, QWidget

from .engineering_shell import EngineeringShellMainWindow


class _LogicalMessageTooltipSuppressor(QObject):
    """Suppress native tooltips only on logical-message table viewports."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        return event.type() == QEvent.Type.ToolTip


class RestorableDockEngineeringShellMainWindow(EngineeringShellMainWindow):
    """Engineering shell with dock actions driven by actual dock visibility.

    Qt can leave a checkable action out of sync after a dock is closed with its
    title-bar close button, especially after restoring a saved workspace. The
    actions below therefore toggle the dock's real hidden state instead of trusting
    the action's incoming ``checked`` value.
    """

    # Stage 1 layout revision 2 removes the left activity toolbar. Reject saved
    # revision-1 state so Qt cannot restore an obsolete empty strip.
    WORKSPACE_STATE_VERSION = 2

    def __init__(self, services) -> None:
        super().__init__(services)
        self._remove_activity_bar()
        self._table_tooltip_suppressor = _LogicalMessageTooltipSuppressor(self)
        self.tabs.currentChanged.connect(self._schedule_tooltip_suppressor_scan)
        QTimer.singleShot(0, self._install_logical_message_tooltip_suppressors)

    def _build_docks(self) -> None:
        super()._build_docks()
        self._rewire_dock_toggle(self.toggle_explorer_action, self.explorer_dock)
        self._rewire_dock_toggle(self.toggle_inspector_action, self.inspector_dock)
        self._rewire_dock_toggle(self.toggle_output_action, self.output_dock)

    def _apply_default_layout(self) -> None:
        super()._apply_default_layout()
        self._remove_activity_bar()

    def _remove_activity_bar(self) -> None:
        activity_bar = getattr(self, "activity_bar", None)
        if activity_bar is None:
            return
        self.removeToolBar(activity_bar)
        activity_bar.hide()

    def _schedule_tooltip_suppressor_scan(self, *_args: object) -> None:
        QTimer.singleShot(0, self._install_logical_message_tooltip_suppressors)

    def _install_logical_message_tooltip_suppressors(self) -> None:
        current = self.tabs.currentWidget()
        if not isinstance(current, QWidget):
            return
        for table in current.findChildren(QTableView):
            if not self._table_uses_logical_message_model(table):
                continue
            viewport = table.viewport()
            if bool(viewport.property("crtLogicalTooltipSuppressed")):
                continue
            viewport.installEventFilter(self._table_tooltip_suppressor)
            viewport.setProperty("crtLogicalTooltipSuppressed", True)

    @staticmethod
    def _table_uses_logical_message_model(table: QTableView) -> bool:
        model = table.model()
        visited: set[int] = set()
        while model is not None and id(model) not in visited:
            visited.add(id(model))
            if "LogicalMessage" in type(model).__name__:
                return True
            source_model = getattr(model, "sourceModel", None)
            model = source_model() if callable(source_model) else None
        return False

    def _rewire_dock_toggle(self, action: QAction, dock: QDockWidget) -> None:
        try:
            action.triggered.disconnect()
        except (RuntimeError, TypeError):
            pass

        action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        action.triggered.connect(
            lambda _checked=False, current_action=action, current_dock=dock: (
                self._toggle_dock(current_action, current_dock)
            )
        )
        dock.visibilityChanged.connect(
            lambda visible, current_action=action: current_action.setChecked(
                bool(visible)
            )
        )
        action.setChecked(not dock.isHidden())

    @staticmethod
    def _toggle_dock(action: QAction, dock: QDockWidget) -> None:
        target_visible = dock.isHidden()
        if target_visible:
            dock.show()
            dock.raise_()
            if dock.isFloating():
                dock.activateWindow()
        else:
            dock.hide()
        action.setChecked(target_visible)
