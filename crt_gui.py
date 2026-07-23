from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _prepare_desktop_qt_platform() -> None:
    """Prevent test-only headless Qt settings from hiding the desktop GUI."""

    if os.environ.get("CRT_HEADLESS") == "1":
        return
    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if platform in {"offscreen", "minimal", "minimalegl"}:
        os.environ.pop("QT_QPA_PLATFORM", None)


def _write_startup_failure() -> None:
    log_path = Path(__file__).resolve().with_name("crt_gui_startup.log")
    log_path.write_text(traceback.format_exc(), encoding="utf-8")


_prepare_desktop_qt_platform()

try:
    from gui.main import main
except BaseException:
    _write_startup_failure()
    raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        _write_startup_failure()
        raise
