from __future__ import annotations

import gc
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from app.capture_service import CaptureState, CaptureStatus
from app.live_buffer import LiveFrameSnapshot
from app.live_capture_controller import CanAdapterInfo
from app.project import CrtProject
from gui.bounded_live_capture import BoundedLiveCaptureWidget


class _Controller:
    def __init__(self) -> None:
        self.message_snapshot_calls = 0
        self.active = True

    @property
    def is_active(self) -> bool:
        return self.active

    def list_adapters(self):
        return [
            CanAdapterInfo(
                number=0,
                name="Virtual CAN",
                serial_number="test",
                product_number="test",
                supports_silent_mode=True,
                is_virtual=True,
            )
        ]

    def status(self) -> CaptureStatus:
        return CaptureStatus(
            state=CaptureState.RUNNING if self.active else CaptureState.STOPPED,
            elapsed_s=0.0,
            frame_count=0,
            logical_message_count=0,
            incomplete_message_count=0,
            marker_count=0,
            unique_can_ids=0,
            adapter_name="Virtual CAN",
            error="",
            paths=None,
            persist_to_disk=False,
            live_capacity=20_000,
            live_retained=0,
            live_dropped_from_view=0,
            live_message_capacity=1,
            live_messages_retained=0,
            live_messages_dropped_from_view=0,
            last_marker=None,
        )

    def frames_since(self, _after_sequence):
        return LiveFrameSnapshot(
            frames=(),
            total_received=0,
            capacity=20_000,
            first_available_sequence=None,
            last_available_sequence=None,
            truncated=False,
            dropped_from_view=0,
        )

    def messages_since(self, _after_sequence):
        self.message_snapshot_calls += 1
        raise AssertionError("Live GUI must not request logical messages")

    def stop(self) -> None:
        self.active = False

    def wait(self, _timeout=None) -> bool:
        return True


def main() -> None:
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as temporary:
        project = CrtProject.create(
            f"{temporary}/project",
            name="Deferred Live",
        )
        controller = _Controller()
        widget = BoundedLiveCaptureWidget(project, controller=controller)
        widget.timer.stop()

        assert widget.message_table.isHidden(), "logical table must stay hidden in Live"
        assert widget.load_deferred_logical_button.text() == "Załaduj"
        assert not widget.load_deferred_logical_button.isEnabled()
        assert widget.LIVE_MESSAGE_CAPACITY == 1

        widget._refresh_view()
        app.processEvents()

        assert controller.message_snapshot_calls == 0, (
            "raw-only Live refresh requested logical messages"
        )
        assert widget.message_model.rowCount() == 0
        assert "nie są analizowane na żywo" in widget.deferred_logical_status.text()

        widget.shutdown()
        widget.close()
        app.processEvents()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        del widget
        del controller
        del project
        gc.collect()


if __name__ == "__main__":
    main()
