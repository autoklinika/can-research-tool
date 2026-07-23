from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gui.application_container import ApplicationContainer


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTProjectPreparationProgressSmoke")
    QSettings().clear()

    window = ApplicationContainer().create_main_window()
    window.show()
    app.processEvents()

    status = window.project_preparation_status
    tracker = window.project_preparation
    assert status.objectName() == "projectPreparationStatus"
    assert status.isHidden()

    tracker.begin_task(
        "fixture-index",
        "Indeks wyszukiwania — Sesja testowa",
        current=0,
        total=100,
    )
    app.processEvents()
    assert not status.isHidden()
    assert status.property("state") == "running"
    assert "Indeks wyszukiwania" in status.label.text()
    assert status.progress_bar.maximum() == 100
    assert status.progress_bar.value() == 0

    tracker.update_task("fixture-index", current=42, total=100)
    app.processEvents()
    assert status.progress_bar.value() == 42

    tracker.complete_task("fixture-index")
    app.processEvents()
    assert status.property("state") == "completed"
    assert status.progress_bar.value() == 1
    assert "Projekt gotowy" in status.label.text()

    tracker.clear()
    app.processEvents()
    assert status.isHidden()

    window.close()
    app.processEvents()
    QSettings().clear()


if __name__ == "__main__":
    main()
