from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .application_container import ApplicationContainer


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("Autoklinika")
    app.setApplicationName("CAN Research Tool")
    container = ApplicationContainer()
    window = container.create_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
