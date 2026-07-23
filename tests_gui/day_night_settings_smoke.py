from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gui.settings_view import SettingsViewWidget
from gui.theme_manager import ColorTheme, THEME_SETTINGS_KEY, apply_color_theme


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTest")
    app.setApplicationName("CRTDayNightSmoke")

    settings = QSettings()
    settings.remove(THEME_SETTINGS_KEY)
    apply_color_theme(app, ColorTheme.NIGHT, persist=True, settings=settings)

    widget = SettingsViewWidget()
    assert widget.night_radio.isChecked()
    assert not widget.day_radio.isChecked()

    widget.day_radio.click()
    app.processEvents()
    assert settings.value(THEME_SETTINGS_KEY, "", str) == ColorTheme.DAY.value
    assert "#f3f5f7" in app.styleSheet()

    widget.night_radio.click()
    app.processEvents()
    assert settings.value(THEME_SETTINGS_KEY, "", str) == ColorTheme.NIGHT.value
    assert "#15191d" in app.styleSheet()

    widget.deleteLater()
    app.processEvents()
    settings.remove(THEME_SETTINGS_KEY)


if __name__ == "__main__":
    main()
