from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMessageBox

from .comparison_sets_shell import ComparisonSetsMainWindow
from .help_center_view import HelpCenterWidget


class HelpCenterMainWindow(ComparisonSetsMainWindow):
    """CRT shell with global, project-independent in-application help."""

    def _build_actions(self) -> None:
        super()._build_actions()

        self.help_action = QAction("Pomoc CRT", self)
        self.help_action.setObjectName("helpCenterAction")
        self.help_action.setShortcut("F1")
        self.help_action.setToolTip(
            "Otwórz przeszukiwalny opis funkcji CAN Research Tool"
        )
        self.help_action.triggered.connect(
            lambda _checked=False: self._open_help("start")
        )

        self.help_quick_start_action = QAction("Szybki start", self)
        self.help_quick_start_action.setObjectName("helpQuickStartAction")
        self.help_quick_start_action.triggered.connect(
            lambda _checked=False: self._open_help("quick-start")
        )

        self.help_glossary_action = QAction("Słownik pojęć", self)
        self.help_glossary_action.setObjectName("helpGlossaryAction")
        self.help_glossary_action.triggered.connect(
            lambda _checked=False: self._open_help("glossary")
        )

        self.help_shortcuts_action = QAction("Skróty klawiaturowe", self)
        self.help_shortcuts_action.setObjectName("helpShortcutsAction")
        self.help_shortcuts_action.triggered.connect(
            lambda _checked=False: self._open_help("shortcuts")
        )

        self.about_action = QAction("O CAN Research Tool", self)
        self.about_action.setObjectName("aboutCrtAction")
        self.about_action.triggered.connect(self._show_about)

    def _build_menu(self) -> None:
        super()._build_menu()
        help_menu = self.menuBar().addMenu("Pomoc")
        help_menu.setObjectName("helpMenu")
        help_menu.addAction(self.help_action)
        help_menu.addAction(self.help_quick_start_action)
        help_menu.addSeparator()
        help_menu.addAction(self.help_glossary_action)
        help_menu.addAction(self.help_shortcuts_action)
        help_menu.addSeparator()
        help_menu.addAction(self.about_action)
        self.help_menu = help_menu

    def _build_activity_bar(self) -> None:
        super()._build_activity_bar()
        self.activity_bar.addSeparator()
        self.activity_bar.addAction(self.help_action)

    def _open_help(self, topic_id: str = "start") -> None:
        key = "help-center"
        existing = self.navigator.widget(key)
        if isinstance(existing, HelpCenterWidget):
            existing.open_topic(topic_id)
            self._activate_tab(key)
            existing.setFocus()
            return

        widget = HelpCenterWidget(self.tabs)
        widget.open_topic(topic_id)
        self._add_tab(key, widget, "Pomoc")
        widget.setFocus()

    def open_help_topic(self, topic_id: str) -> None:
        """Public hook for future context-sensitive Help buttons."""
        self._open_help(topic_id)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "O CAN Research Tool",
            "<h3>CAN Research Tool</h3>"
            "<p>Projektowe środowisko do rejestracji, organizowania i "
            "pasywnej analizy komunikacji CAN.</p>"
            "<p>Surowe sesje pozostają źródłem prawdy, a analizy tworzą "
            "wersjonowane artefakty prowadzące do dokładnych dowodów.</p>"
            "<p>Naciśnij <b>F1</b>, aby otworzyć pełną pomoc.</p>",
        )


__all__ = ["HelpCenterMainWindow"]
