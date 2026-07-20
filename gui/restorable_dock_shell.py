from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QStyle,
    QTableView,
    QToolButton,
    QWidget,
)

from .engineering_shell import EngineeringShellMainWindow


class _LogicalMessageTooltipSuppressor(QObject):
    """Suppress native tooltips only on logical-message table viewports."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        return event.type() == QEvent.Type.ToolTip


class _ProjectDockTitleBar(QWidget):
    """Compact title bar with float, collapse and close controls."""

    def __init__(
        self,
        dock: QDockWidget,
        collapse_requested: Callable[[], None],
    ) -> None:
        super().__init__(dock)
        self._dock = dock
        self.setObjectName("projectDockTitleBar")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(2)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        title = QLabel(dock.windowTitle(), self)
        title.setObjectName("projectDockTitle")
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(title, 1)

        style = dock.style()
        standard = QStyle.StandardPixmap

        self.float_button = self._button(
            "projectDockFloatButton",
            style.standardIcon(standard.SP_TitleBarNormalButton),
            self._toggle_floating,
        )
        layout.addWidget(self.float_button)

        self.collapse_button = self._button(
            "projectDockCollapseButton",
            style.standardIcon(standard.SP_ArrowLeft),
            collapse_requested,
        )
        self.collapse_button.setToolTip("Zwiń panel Projekt")
        layout.addWidget(self.collapse_button)

        self.close_button = self._button(
            "projectDockCloseButton",
            style.standardIcon(standard.SP_TitleBarCloseButton),
            dock.close,
        )
        self.close_button.setToolTip("Zamknij panel Projekt")
        layout.addWidget(self.close_button)

        dock.topLevelChanged.connect(self._sync_float_tooltip)
        dock.windowTitleChanged.connect(title.setText)
        self._sync_float_tooltip(dock.isFloating())

    def _button(
        self,
        object_name: str,
        icon,
        callback: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setAutoRaise(True)
        button.setIcon(icon)
        button.setFixedSize(22, 22)
        button.clicked.connect(callback)
        return button

    def _toggle_floating(self) -> None:
        self._dock.setFloating(not self._dock.isFloating())

    def _sync_float_tooltip(self, floating: bool) -> None:
        self.float_button.setToolTip(
            "Dokuj panel Projekt" if floating else "Odepnij panel Projekt"
        )


class RestorableDockEngineeringShellMainWindow(EngineeringShellMainWindow):
    """Engineering shell with compact, restorable project and inspector docks."""

    # Revision 6 adds an opt-in main toolbar alongside the opt-in Inspector.
    WORKSPACE_STATE_VERSION = 6

    def __init__(self, services) -> None:
        super().__init__(services)
        self._remove_activity_bar()
        self._remove_output_panel()
        self._hide_primary_toolbar_by_default()
        self._table_tooltip_suppressor = _LogicalMessageTooltipSuppressor(self)
        self.tabs.currentChanged.connect(self._schedule_tooltip_suppressor_scan)
        QTimer.singleShot(0, self._install_logical_message_tooltip_suppressors)

    def _build_actions(self) -> None:
        super()._build_actions()
        self.toggle_primary_toolbar_action = QAction("Narzędzia główne", self)
        self.toggle_primary_toolbar_action.setObjectName("togglePrimaryToolbarAction")
        self.toggle_primary_toolbar_action.setCheckable(True)
        self.toggle_primary_toolbar_action.setChecked(False)
        self.toggle_primary_toolbar_action.setToolTip(
            "Pokaż lub ukryj pasek Narzędzia główne"
        )

    def _build_menu(self) -> None:
        super()._build_menu()
        view_menu = None
        for menu_action in reversed(self.menuBar().actions()):
            if menu_action.text().replace("&", "") != "Widok":
                continue
            candidate = menu_action.menu()
            if candidate is None:
                continue
            try:
                candidate.actions()
            except RuntimeError:
                continue
            view_menu = candidate
            break
        if view_menu is None:
            raise RuntimeError("Nie można zbudować menu Widok")
        view_menu.insertAction(
            self.reset_layout_action,
            self.toggle_primary_toolbar_action,
        )

    def _build_activity_bar(self) -> None:
        super()._build_activity_bar()
        self.toggle_primary_toolbar_action.toggled.connect(
            self.primary_toolbar.setVisible
        )
        self.primary_toolbar.visibilityChanged.connect(
            self.toggle_primary_toolbar_action.setChecked
        )
        self.toggle_primary_toolbar_action.setChecked(
            not self.primary_toolbar.isHidden()
        )

    def _set_capture_status(self, text: str) -> None:
        """Update the indicator without rebuilding native Qt style internals."""

        normalized = (text or "STOPPED").strip()
        upper = normalized.upper()
        if "ERROR" in upper or "BŁĄD" in upper:
            state = "error"
            foreground, background = "#a32121", "#fbe8e8"
        elif "CONNECT" in upper or "ŁĄCZ" in upper:
            state = "connecting"
            foreground, background = "#8a5a00", "#fff4d6"
        elif (
            "CAPTUR" in upper
            or "RECORD" in upper
            or "RUNNING" in upper
            or "AKTYW" in upper
        ):
            state = "running"
            foreground, background = "#176b35", "#e5f4ea"
        else:
            state = "stopped"
            foreground, background = "#5c636b", "transparent"

        self.capture_status.setText(normalized)
        self.capture_indicator.setText(normalized)
        self.capture_indicator.setProperty("state", state)
        self.capture_indicator.setStyleSheet(
            "QLabel#captureIndicator {"
            f"color: {foreground}; background: {background};"
            "border-left: 1px solid #c9cdd2; padding: 2px 10px;"
            "min-width: 78px; font-weight: 600;"
            "}"
        )

    def _build_docks(self) -> None:
        super()._build_docks()
        self._rewire_dock_toggle(self.toggle_explorer_action, self.explorer_dock)
        self._rewire_dock_toggle(self.toggle_inspector_action, self.inspector_dock)
        self._install_project_title_bar()
        self._remove_output_panel()

    def _set_project(self, project) -> None:
        inspector_was_visible = not self.inspector_dock.isHidden()
        super()._set_project(project)
        if not inspector_was_visible:
            self._hide_inspector_by_default()

    def _apply_default_layout(self) -> None:
        super()._apply_default_layout()
        self._remove_activity_bar()
        self._remove_output_panel()
        self._hide_inspector_by_default()
        self._hide_primary_toolbar_by_default()

    def _hide_primary_toolbar_by_default(self) -> None:
        toolbar = getattr(self, "primary_toolbar", None)
        if toolbar is not None:
            toolbar.hide()
        action = getattr(self, "toggle_primary_toolbar_action", None)
        if action is not None:
            action.setChecked(False)

    def _install_project_title_bar(self) -> None:
        dock = self.explorer_dock
        if bool(dock.property("crtCustomTitleBarInstalled")):
            return

        self.project_dock_title_bar = _ProjectDockTitleBar(
            dock,
            self._collapse_project_dock,
        )
        dock.setTitleBarWidget(self.project_dock_title_bar)
        dock.setProperty("crtCustomTitleBarInstalled", True)

    def _collapse_project_dock(self) -> None:
        """Hide Project immediately; Ctrl+B or View -> Project restores it."""

        self.explorer_dock.hide()
        self.toggle_explorer_action.setChecked(False)

    def _hide_inspector_by_default(self) -> None:
        self.inspector_dock.hide()
        self.toggle_inspector_action.setChecked(False)

    def _remove_activity_bar(self) -> None:
        activity_bar = getattr(self, "activity_bar", None)
        if activity_bar is None:
            return
        self.removeToolBar(activity_bar)
        activity_bar.hide()

    def _remove_output_panel(self) -> None:
        """Keep the diagnostic sink alive but remove its visible dock and action."""

        action = getattr(self, "toggle_output_action", None)
        if action is not None:
            # The old signal can stay connected because a hidden, disabled action can
            # never be invoked by the user. Avoiding disconnect() also avoids a noisy
            # PySide warning when this idempotent method runs more than once.
            action.setShortcut("")
            action.setChecked(False)
            action.setEnabled(False)
            action.setVisible(False)

        dock = getattr(self, "output_dock", None)
        if dock is None:
            return
        dock.hide()
        self.removeDockWidget(dock)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setAllowedAreas(Qt.DockWidgetArea.NoDockWidgetArea)

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
