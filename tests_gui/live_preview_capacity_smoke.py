from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication

from app.project import CrtProject
from gui.application_container import ApplicationContainer
from gui.bounded_live_capture import (
    LIVE_PREVIEW_FRAME_CAPACITY,
    LIVE_PREVIEW_MESSAGE_CAPACITY,
    BoundedLiveCaptureWidget,
)


class FakeLiveController:
    def list_adapters(self):
        return []

    @property
    def is_active(self) -> bool:
        return False


def main() -> None:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(Path(temporary) / "project", name="Live Preview")
        container = ApplicationContainer(live_controller_factory=FakeLiveController)
        view = container.create_live_capture_view(project)

        assert isinstance(view, BoundedLiveCaptureWidget)
        assert view.LIVE_CAPACITY == LIVE_PREVIEW_FRAME_CAPACITY == 20_000
        assert view.LIVE_MESSAGE_CAPACITY == LIVE_PREVIEW_MESSAGE_CAPACITY == 1
        assert view.frame_model.capacity == 20_000
        assert view.message_model._capacity == 1
        assert not hasattr(view, "performance_panel")
        assert not hasattr(view, "performance_label")

        view.close()

    app.quit()


if __name__ == "__main__":
    main()
