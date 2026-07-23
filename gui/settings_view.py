from __future__ import annotations

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QGroupBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from .theme_manager import ColorTheme, apply_color_theme, current_theme


class SettingsViewWidget(QWidget):
    """Application settings with immediate, persisted theme switching."""

    output_message = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsView")
        self._settings = QSettings()
        self._updating = False
        self._build_ui()
        self._load_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        title = QLabel("Ustawienia")
        title.setObjectName("projectOverviewTitle")
        root.addWidget(title)

        description = QLabel(
            "Ustawienia interfejsu są zapisywane automatycznie i odtwarzane "
            "przy kolejnym uruchomieniu programu."
        )
        description.setWordWrap(True)
        description.setObjectName("secondaryText")
        root.addWidget(description)

        appearance_group = QGroupBox("Wygląd")
        appearance_layout = QVBoxLayout(appearance_group)
        appearance_layout.setSpacing(8)

        appearance_layout.addWidget(QLabel("Tryb kolorystyczny:"))
        self.day_radio = QRadioButton("Day — jasny")
        self.day_radio.setObjectName("dayThemeRadio")
        self.night_radio = QRadioButton("Night — ciemny")
        self.night_radio.setObjectName("nightThemeRadio")

        self.theme_group = QButtonGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_group.addButton(self.day_radio)
        self.theme_group.addButton(self.night_radio)

        appearance_layout.addWidget(self.day_radio)
        appearance_layout.addWidget(self.night_radio)

        note = QLabel(
            "Zmiana jest stosowana natychmiast do całej aplikacji. "
            "Nie wymaga ponownego uruchomienia."
        )
        note.setWordWrap(True)
        note.setObjectName("secondaryText")
        appearance_layout.addWidget(note)
        root.addWidget(appearance_group)
        root.addStretch(1)

        self.day_radio.toggled.connect(self._theme_changed)
        self.night_radio.toggled.connect(self._theme_changed)

    def _load_state(self) -> None:
        self._updating = True
        selected = current_theme(self._settings)
        self.day_radio.setChecked(selected is ColorTheme.DAY)
        self.night_radio.setChecked(selected is ColorTheme.NIGHT)
        self._updating = False

    def _theme_changed(self, checked: bool) -> None:
        if self._updating or not checked:
            return
        app = QApplication.instance()
        if app is None:
            return
        selected = ColorTheme.DAY if self.day_radio.isChecked() else ColorTheme.NIGHT
        apply_color_theme(app, selected, persist=True, settings=self._settings)
        label = "Day" if selected is ColorTheme.DAY else "Night"
        self.output_message.emit(f"Zmieniono tryb interfejsu na {label}")
