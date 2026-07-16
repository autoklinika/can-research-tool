from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .filter_integration import install_filter_integration
from .live_filter_integration import install_live_filter_integration
from .main_window import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("Autoklinika")
    app.setApplicationName("CAN Research Tool")
    install_filter_integration()
    install_live_filter_integration()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
