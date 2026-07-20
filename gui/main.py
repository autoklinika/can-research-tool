from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from .application_container import ApplicationContainer
from .engineering_theme import apply_engineering_theme

_CLEAN_SHUTDOWN_KEY = "runtime/lastShutdownClean"
_LAYOUT_MIGRATION_KEY = "ui/engineeringShellSafeRestoreVersion"
_LAYOUT_MIGRATION_VERSION = 2
_WORKSPACE_KEYS = (
    "ui/engineeringShellGeometry",
    "ui/engineeringShellState",
)
_STARTUP_LOG = Path(__file__).resolve().parent.parent / "crt_gui_startup.log"


def _checkpoint(message: str) -> None:
    """Persist startup progress even when Qt terminates the process natively."""

    with _STARTUP_LOG.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _prepare_startup_settings() -> QSettings:
    """Reset only the dock workspace after an unclean/native Qt shutdown."""

    settings = QSettings()
    previous_clean = settings.value(_CLEAN_SHUTDOWN_KEY, True, type=bool)
    migration_version = settings.value(_LAYOUT_MIGRATION_KEY, 0, type=int)

    if not previous_clean or migration_version < _LAYOUT_MIGRATION_VERSION:
        for key in _WORKSPACE_KEYS:
            settings.remove(key)
        settings.setValue(_LAYOUT_MIGRATION_KEY, _LAYOUT_MIGRATION_VERSION)

    settings.setValue(_CLEAN_SHUTDOWN_KEY, False)
    settings.sync()
    return settings


def main() -> int:
    _STARTUP_LOG.write_text("CRT startup\n", encoding="utf-8")
    _checkpoint("01 before QApplication")
    app = QApplication.instance() or QApplication(sys.argv)
    _checkpoint("02 QApplication ready")

    app.setOrganizationName("Autoklinika")
    app.setApplicationName("CAN Research Tool")
    _checkpoint("03 identity ready")

    # Keep the engineering QSS and typography, but do not replace the global
    # Windows style engine with Fusion. Installing Fusion globally has produced
    # unrecoverable native aborts before the first window is constructed.
    apply_engineering_theme(app)
    _checkpoint("04 engineering theme ready")

    startup_settings = _prepare_startup_settings()
    _checkpoint("05 settings ready")

    container = ApplicationContainer()
    _checkpoint("06 container ready")
    window = container.create_main_window()
    _checkpoint("07 main window constructed")
    window.show()
    _checkpoint("08 main window shown")

    exit_code = app.exec()
    _checkpoint(f"09 event loop finished: {exit_code}")

    startup_settings.setValue(_CLEAN_SHUTDOWN_KEY, True)
    startup_settings.sync()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
