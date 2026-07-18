from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication

from app.project import CrtProject
from gui.application_container import ApplicationContainer
from gui.stage_h_live_capture import (
    STAGE_H_FRAME_CAPACITY,
    STAGE_H_MESSAGE_CAPACITY,
    StageHLiveCaptureWidget,
)


class FakeLiveController:
    def list_adapters(self):
        return []

    @property
    def is_active(self) -> bool:
        return False


def main() -> None:
    os.environ["CRT_LIVE_PERF"] = "1"
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(Path(temporary) / "project", name="Stage H")
        container = ApplicationContainer(live_controller_factory=FakeLiveController)
        view = container.create_live_capture_view(project)

        assert isinstance(view, StageHLiveCaptureWidget)
        assert view.LIVE_CAPACITY == STAGE_H_FRAME_CAPACITY == 20_000
        assert view.LIVE_MESSAGE_CAPACITY == STAGE_H_MESSAGE_CAPACITY == 5_000
        assert view.frame_model.capacity == 20_000
        assert view.message_model._capacity == 5_000
        assert not hasattr(view, "performance_panel")
        assert not hasattr(view, "performance_label")

        view.close()

    app.quit()


if __name__ == "__main__":
    main()
