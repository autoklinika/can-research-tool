from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QDir, QProcess, QUrl
from PySide6.QtGui import QDesktopServices


def reveal_path(path: str | Path) -> bool:
    """Reveal a local path using the platform's desktop file manager."""

    target = Path(path)
    native = QDir.toNativeSeparators(str(target))
    if sys.platform.startswith("win"):
        return _process_started(
            QProcess.startDetached("explorer.exe", [f"/select,{native}"])
        )
    if sys.platform == "darwin":
        return _process_started(QProcess.startDetached("open", ["-R", str(target)]))
    location = target.parent if target.parent.is_dir() else target
    return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(location))))


def _process_started(result: object) -> bool:
    if isinstance(result, tuple):
        return bool(result[0]) if result else False
    return bool(result)
