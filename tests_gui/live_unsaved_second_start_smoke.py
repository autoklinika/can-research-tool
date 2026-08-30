from __future__ import annotations

import gc
import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication

from app.capture_service import CapturePaths, CaptureState, CaptureStatus
from app.live_capture_controller import CanAdapterInfo
from app.models import CanFrame
from app.project import CrtProject
from gui.application_container import ApplicationContainer


class _Controller:
    def __init__(self) -> None:
        self.start_calls = 0
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

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

    def start(self, request):
        self.start_calls += 1
        self._active = True
        base = request.output_dir / request.session_name
        return CapturePaths(
            session=Path(str(base) + ".crt.jsonl"),
            raw_frames_csv=Path(str(base) + ".frames.csv"),
            logical_messages_csv=Path(str(base) + ".messages.csv"),
            markers=Path(str(base) + ".markers.jsonl"),
        )

    def stop(self) -> None:
        self._active = False

    def wait(self, _timeout=None) -> bool:
        return True


def _drain_deferred_deletes(app: QApplication) -> None:
    QThreadPool.globalInstance().waitForDone(5_000)
    for _ in range(5):
        app.sendPostedEvents()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("Autoklinika-tests")
    app.setApplicationName("CRT-live-unsaved-second-start")

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(Path(temporary) / "project", name="Second Start")
        controller = _Controller()
        container = ApplicationContainer(
            live_controller_factory=lambda: controller,
        )
        live = container.create_live_capture_view(project)
        live.timer.stop()

        temp_dir = project.root / ".crt" / "temp" / "live"
        temp_dir.mkdir(parents=True, exist_ok=True)
        old_paths = CapturePaths(
            session=temp_dir / "old_log.crt.jsonl",
            raw_frames_csv=temp_dir / "old_log.frames.csv",
            logical_messages_csv=temp_dir / "old_log.messages.csv",
            markers=temp_dir / "old_log.markers.jsonl",
        )
        old_paths.session.write_text('{"record":"session"}\n', encoding="utf-8")

        old_status = CaptureStatus(
            state=CaptureState.STOPPED,
            elapsed_s=2.0,
            frame_count=1,
            logical_message_count=0,
            incomplete_message_count=0,
            marker_count=1,
            unique_can_ids=1,
            adapter_name="Virtual CAN",
            error="",
            paths=old_paths,
            persist_to_disk=True,
            live_capacity=20_000,
            live_retained=1,
            live_dropped_from_view=0,
            live_message_capacity=1,
            live_messages_retained=0,
            live_messages_dropped_from_view=0,
            last_marker=None,
        )

        integration = live._live_save_integration
        integration._pending_paths = old_paths
        integration._pending_status = old_status
        integration._pending_name = "old_log"
        integration._transient_finalized = True
        live._analysis_session_path = old_paths.session
        live.frame_model.append_frames(
            (
                CanFrame(
                    sequence=1,
                    timestamp_ns=1_000_000,
                    arbitration_id=0x123,
                    data=b"\x01",
                ),
            )
        )
        live.marker_history.addItem("1.000 ms  TEST")

        integration.confirm_pending_log = (
            lambda *, reason: integration.discard_pending_log()
        )

        # First Start resolves the old log and clears the workspace only.
        live._start_capture()
        app.processEvents()
        assert controller.start_calls == 0
        assert not controller.is_active
        assert not integration.has_unsaved_log
        assert live.frame_model.frame_count == 0
        assert live.message_model.rowCount() == 0
        assert live.marker_history.count() == 0
        assert live._deferred_start_ready
        assert "Start ponownie" in live.deferred_logical_status.text()
        assert live.received_label.text() == "Odebrane: 0"

        # The second deliberate Start begins capture.
        live._start_capture()
        app.processEvents()
        assert controller.start_calls == 1
        assert controller.is_active
        assert not live._deferred_start_ready
        assert "Rejestracja trwa" in live.deferred_logical_status.text()

        live.shutdown()
        live.close()
        live.deleteLater()
        _drain_deferred_deletes(app)

        integration = None
        live = None
        container = None
        project = None
        controller = None
        gc.collect()
        _drain_deferred_deletes(app)


if __name__ == "__main__":
    main()
