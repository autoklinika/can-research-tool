from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .application_container import ApplicationContainer
from .engineering_theme import apply_engineering_theme


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("Autoklinika")
    app.setApplicationName("CAN Research Tool")
    apply_engineering_theme(app)
    container = ApplicationContainer()
    window = container.create_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
