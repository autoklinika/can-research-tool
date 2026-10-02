from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from .live_capture import LiveCaptureWidget

if TYPE_CHECKING:
    from .main_window import MainWindow


class LiveLogSaveController(QObject):
    """Explicit promotion of the finished temporary Live log to a project session."""

    save_available_changed = Signal(bool)

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window

    def bind(self, widget: LiveCaptureWidget) -> None:
        widget.status_text.connect(lambda _text: self.sync())
        widget.project_changed.connect(self.sync)

    def live_widget(self) -> LiveCaptureWidget | None:
        widget = self._window.navigator.widget("live-capture")
        return widget if isinstance(widget, LiveCaptureWidget) else None

    def has_unsaved_log(self) -> bool:
        widget = self.live_widget()
        return bool(widget is not None and widget.save_integration.has_unsaved_log)

    def sync(self) -> None:
        widget = self.live_widget()
        self.save_available_changed.emit(
            bool(
                widget is not None
                and not widget.is_capturing
                and widget.save_integration.has_unsaved_log
            )
        )

    def save_pending(self) -> None:
        widget = self.live_widget()
        if widget is None:
            self.sync()
            return
        widget.save_integration.save_pending_log()
        self._window.explorer.refresh()
        self.sync()

    def confirm_unsaved(self, reason: str) -> bool:
        """Ask what to do with an unsaved log; False means the user cancelled."""

        if not self.has_unsaved_log():
            return True
        widget = self.live_widget()
        assert widget is not None
        accepted = bool(widget.save_integration.confirm_pending_log(reason=reason))
        self._window.explorer.refresh()
        self.sync()
        return accepted
