from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from .application_container import ApplicationContainer
from .engineering_theme import apply_engineering_theme

_CLEAN_SHUTDOWN_KEY = "runtime/lastShutdownClean"
_LAYOUT_MIGRATION_KEY = "ui/engineeringShellSafeRestoreVersion"
_LAYOUT_MIGRATION_VERSION = 1
_WORKSPACE_KEYS = (
    "ui/engineeringShellGeometry",
    "ui/engineeringShellState",
)


def _prepare_startup_settings() -> QSettings:
    """Reset only the dock workspace after an unclean/native Qt shutdown."""

    settings = QSettings()
    previous_clean = settings.value(_CLEAN_SHUTDOWN_KEY, True, type=bool)
    migration_version = settings.value(_LAYOUT_MIGRATION_KEY, 0, type=int)

    if not previous_clean or migration_version < _LAYOUT_MIGRATION_VERSION:
        for key in _WORKSPACE_KEYS:
            settings.remove(key)
        settings.setValue(_LAYOUT_MIGRATION_KEY, _LAYOUT_MIGRATION_VERSION)

    # Persist before constructing/showing the main window. A native Qt abort does
    # not unwind Python, so the False marker survives and forces a safe layout on
    # the next launch.
    settings.setValue(_CLEAN_SHUTDOWN_KEY, False)
    settings.sync()
    return settings


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("Autoklinika")
    app.setApplicationName("CAN Research Tool")
    app.setStyle("Fusion")
    apply_engineering_theme(app)

    startup_settings = _prepare_startup_settings()
    container = ApplicationContainer()
    window = container.create_main_window()
    window.show()
    exit_code = app.exec()

    startup_settings.setValue(_CLEAN_SHUTDOWN_KEY, True)
    startup_settings.sync()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
