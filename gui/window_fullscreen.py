from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QWidget


class FullScreenController(QObject):
    """Window-local F11 toggle that restores the previous normal/maximized state."""

    def __init__(
        self,
        window: QWidget,
        *,
        action_object_name: str,
        maximize_button: bool = False,
    ) -> None:
        super().__init__(window)
        self.window = window
        self._restore_maximized = False

        if maximize_button:
            window.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        self.action = QAction("Pełny ekran", window)
        self.action.setObjectName(action_object_name)
        self.action.setCheckable(True)
        self.action.setShortcut(QKeySequence("F11"))
        self.action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.action.setToolTip("Włącz lub wyłącz pełny ekran (F11)")
        self.action.triggered.connect(self._action_triggered)
        window.addAction(self.action)

    @Slot(bool)
    def _action_triggered(self, _checked: bool = False) -> None:
        self.toggle()

    @Slot()
    def toggle(self) -> None:
        if self.window.isFullScreen():
            if self._restore_maximized:
                self.window.showMaximized()
            else:
                self.window.showNormal()
        else:
            self._restore_maximized = self.window.isMaximized()
            self.window.showFullScreen()
        self.action.setChecked(self.window.isFullScreen())


def enable_full_screen(
    window: QWidget,
    *,
    action_object_name: str,
    maximize_button: bool = False,
) -> FullScreenController:
    """Install one reusable F11 controller on a top-level CRT window."""

    controller = FullScreenController(
        window,
        action_object_name=action_object_name,
        maximize_button=maximize_button,
    )
    window.setProperty("crtFullScreenEnabled", True)
    return controller


__all__ = ["FullScreenController", "enable_full_screen"]
