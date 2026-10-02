from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt
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


class LogicalMessageTooltipSuppressor(QObject):
    """Suppress native tooltips only on logical-message table viewports."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        return event.type() == QEvent.Type.ToolTip

    def attach_to_tables_in(self, root: QWidget) -> None:
        for table in root.findChildren(QTableView):
            if not table_uses_logical_message_model(table):
                continue
            viewport = table.viewport()
            if bool(viewport.property("crtLogicalTooltipSuppressed")):
                continue
            viewport.installEventFilter(self)
            viewport.setProperty("crtLogicalTooltipSuppressed", True)


def table_uses_logical_message_model(table: QTableView) -> bool:
    model = table.model()
    visited: set[int] = set()
    while model is not None and id(model) not in visited:
        visited.add(id(model))
        if "LogicalMessage" in type(model).__name__:
            return True
        source_model = getattr(model, "sourceModel", None)
        model = source_model() if callable(source_model) else None
    return False


class ProjectDockTitleBar(QWidget):
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


def bind_dock_toggle(action: QAction, dock: QDockWidget) -> None:
    """Keep a checkable View action and a dock's real visibility in sync."""

    action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    action.triggered.connect(
        lambda _checked=False: _toggle_dock(action, dock)
    )
    dock.visibilityChanged.connect(
        lambda visible: action.setChecked(bool(visible))
    )
    action.setChecked(not dock.isHidden())


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
