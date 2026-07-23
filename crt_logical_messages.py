from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from gui.engineering_theme import apply_engineering_theme
from gui.logical_message_viewer import LogicalMessageViewerWindow


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CRT logical-message sidecar viewer")
    parser.add_argument("session", type=Path)
    parser.add_argument("--dbc", action="append", default=[], type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("Autoklinika")
    app.setApplicationName("CAN Research Tool — Logical Messages")
    apply_engineering_theme(app)

    window = LogicalMessageViewerWindow(
        args.session,
        dbc_paths=tuple(args.dbc),
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
