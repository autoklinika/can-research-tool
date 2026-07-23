from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from .application_container import ApplicationContainer
from .theme_manager import apply_saved_theme

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


def _cleanup_live_temp(settings: QSettings) -> None:
    """Remove deferred Live Capture artifacts after all GUI sessions are closed."""

    project_path = settings.value("project/lastPath", "", str).strip()
    if not project_path:
        return

    live_temp_dir = Path(project_path) / ".crt" / "temp" / "live"
    if not live_temp_dir.exists():
        return

    shutil.rmtree(live_temp_dir)
    _checkpoint(f"10 removed Live temp directory: {live_temp_dir}")


def main() -> int:
    _STARTUP_LOG.write_text("CRT startup\n", encoding="utf-8")
    _checkpoint("01 before QApplication")
    app = QApplication.instance() or QApplication(sys.argv)
    _checkpoint("02 QApplication ready")

    app.setOrganizationName("Autoklinika")
    app.setApplicationName("CAN Research Tool")
    _checkpoint("03 identity ready")

    startup_settings = _prepare_startup_settings()
    _checkpoint("04 settings ready")

    # Keep the native Qt/Windows renderer. The persisted Day/Night theme changes
    # only the application palette and QSS, without replacing the platform style.
    apply_saved_theme(app, startup_settings)
    _checkpoint("05 engineering theme ready")

    container = ApplicationContainer()
    _checkpoint("06 container ready")
    window = container.create_main_window()
    _checkpoint("07 main window constructed")
    window.show()
    _checkpoint("08 main window shown")

    exit_code = app.exec()
    _checkpoint(f"09 event loop finished: {exit_code}")

    try:
        _cleanup_live_temp(startup_settings)
    except OSError as exc:
        _checkpoint(f"10 Live temp cleanup failed: {exc}")

    startup_settings.setValue(_CLEAN_SHUTDOWN_KEY, True)
    startup_settings.sync()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
