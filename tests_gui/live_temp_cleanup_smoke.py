from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication, QSettings

from gui.main import _cleanup_live_temp


def main() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])

    with TemporaryDirectory() as temp_root:
        root = Path(temp_root)
        project_root = root / "project"
        live_dir = project_root / ".crt" / "temp" / "live"
        live_dir.mkdir(parents=True)
        (live_dir / "capture.crt.jsonl").write_text("test\n", encoding="utf-8")
        (live_dir / "capture.logical.sqlite").write_bytes(b"sqlite")

        settings_path = root / "settings.ini"
        settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        settings.setValue("project/lastPath", str(project_root))
        settings.sync()

        _cleanup_live_temp(settings)

        assert not live_dir.exists()
        assert project_root.exists()
        assert (project_root / ".crt" / "temp").exists()

    app.processEvents()


if __name__ == "__main__":
    main()
