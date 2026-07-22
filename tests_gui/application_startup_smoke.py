from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

from gui.application_container import ApplicationContainer
from gui.engineering_theme import apply_engineering_theme


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTApplicationStartupSmoke")
    QSettings().clear()
    apply_engineering_theme(app)

    window = ApplicationContainer().create_main_window()
    window.show()
    app.processEvents()

    assert window.isVisible()
    assert window.objectName() == "engineeringMainWindow"
    assert window.full_screen_action.shortcut().toString() == "F11"
    assert window.full_screen_action in window.actions()

    window.full_screen_action.trigger()
    app.processEvents()
    assert window.isFullScreen()
    window.full_screen_action.trigger()
    app.processEvents()
    assert not window.isFullScreen()

    started = time.monotonic()
    QTimer.singleShot(250, app.quit)
    exit_code = app.exec()
    elapsed = time.monotonic() - started

    assert exit_code == 0
    assert elapsed >= 0.15, f"Qt event loop exited too early: {elapsed:.3f}s"

    window.close()
    QSettings().clear()
    print("Application startup GUI smoke: OK")


if __name__ == "__main__":
    main()
