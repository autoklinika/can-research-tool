from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMessageBox

from .help_center_view import HelpCenterWidget

if TYPE_CHECKING:
    from .main_window import MainWindow


_TAB_KEY = "help-center"


class HelpCenterController(QObject):
    """Global, project-independent in-application help."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window

    def open(self, topic_id: str = "") -> None:
        navigator = self._window.navigator
        existing = navigator.widget(_TAB_KEY)
        if isinstance(existing, HelpCenterWidget):
            if topic_id:
                existing.open_topic(topic_id)
            else:
                existing.show_home()
            navigator.activate(_TAB_KEY)
            existing.setFocus()
            return

        widget = HelpCenterWidget(self._window.tabs)
        if topic_id:
            widget.open_topic(topic_id)
        navigator.add_tab(_TAB_KEY, widget, "Pomoc")
        widget.setFocus()

    def show_about(self) -> None:
        QMessageBox.about(
            self._window,
            "O CAN Research Tool",
            "<h3>CAN Research Tool</h3>"
            "<p>Projektowe środowisko do rejestracji, organizowania i "
            "pasywnej analizy komunikacji CAN.</p>"
            "<p>Surowe sesje pozostają źródłem prawdy, a analizy tworzą "
            "wersjonowane artefakty prowadzące do dokładnych dowodów.</p>"
            "<p>Naciśnij <b>F1</b>, aby otworzyć pełną pomoc.</p>",
        )
