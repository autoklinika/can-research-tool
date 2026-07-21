from __future__ import annotations

from gc import collect
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication

from app.capture_service import CaptureState
from app.filters import FilterMode, FilterPreset, ProjectFilterRepository
from app.logical_records import LogicalMessageRecord
from app.models import CanFrame
from app.project import CrtProject
from gui.live_capture import LiveCaptureWidget
from gui.streaming_live_filter_integration import StreamingLiveFilterIntegration


class _ActiveController:
    @property
    def is_active(self) -> bool:
        return True

    def list_adapters(self):
        return []

    def status(self):
        return SimpleNamespace(
            state=CaptureState.RUNNING,
            elapsed_s=1.0,
            frame_count=30_000,
            logical_message_count=1,
            marker_count=0,
            unique_can_ids=2,
            live_dropped_from_view=0,
            live_retained=30_000,
            live_capacity=250_000,
            error="",
        )

    def frames_since(self, _after_sequence):
        return SimpleNamespace(
            frames=(),
            truncated=False,
            last_available_sequence=None,
        )

    def messages_since(self, _after_sequence):
        return SimpleNamespace(
            messages=(),
            truncated=False,
            last_available_sequence=None,
        )

    def stop(self) -> None:
        return None

    def wait(self, _timeout=None) -> bool:
        return True


def _logical_message(sequence: int) -> LogicalMessageRecord:
    return LogicalMessageRecord(
        sequence=sequence,
        first_timestamp_ns=sequence * 1_000,
        last_timestamp_ns=sequence * 1_000,
        protocol="uds",
        transport="isotp",
        name="ReadDataByIdentifier",
        arbitration_id=0x100,
        is_extended_id=False,
        pgn=None,
        source_address=None,
        destination_address=None,
        complete=True,
        frame_sequences=(sequence,),
        payload=b"\x22\xF1\x90",
    )


def _dispose_widget(app: QApplication, widget: LiveCaptureWidget) -> None:
    widget.shutdown()
    for timer in widget.findChildren(QTimer):
        timer.stop()
    QThreadPool.globalInstance().waitForDone(5_000)
    widget.close()
    # Deliver worker completions and queued callbacks while the project path and
    # widget hierarchy are still valid.
    app.processEvents()
    for timer in widget.findChildren(QTimer):
        timer.stop()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def main() -> None:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Live filter worker")
        preset = FilterPreset.create("Only 0x100")
        preset.enabled = True
        preset.mode = FilterMode.INCLUDE
        preset.scope = ["live"]
        preset.root = {
            "type": "group",
            "operator": "and",
            "children": [
                {
                    "type": "condition",
                    "field": "can_id",
                    "operator": "eq",
                    "values": ["0x100"],
                }
            ],
        }
        repository = ProjectFilterRepository(project.database_path)
        repository.save_presets([preset])

        # When capture is stopped, the original background scan remains available.
        widget = LiveCaptureWidget(project)
        assert widget._live_filter_integration.proxy is widget.live_filter_proxy
        assert widget.frame_table.model() is widget.frame_model
        frames = [
            CanFrame(
                sequence=index,
                timestamp_ns=index * 1_000,
                arbitration_id=0x100 if index % 2 == 0 else 0x200,
                data=b"\x00",
            )
            for index in range(20_000)
        ]
        widget.frame_model.append_frames(frames)
        assert widget.live_filter_proxy.rowCount() == 20_000

        widget.live_filter_proxy.reload_project_filters()
        heartbeat_count = 0

        def heartbeat() -> None:
            nonlocal heartbeat_count
            heartbeat_count += 1

        heartbeat_timer = QTimer()
        heartbeat_timer.setInterval(1)
        heartbeat_timer.timeout.connect(heartbeat)
        heartbeat_timer.start()
        widget.apply_live_filters.setChecked(True)
        assert widget.frame_table.model() is widget.frame_model
        assert widget.live_filter_proxy.filter_scanning is True

        deadline = monotonic() + 10.0
        while not widget.live_filter_proxy.filter_ready and monotonic() < deadline:
            app.processEvents()
            sleep(0.001)

        app.processEvents()
        assert widget.live_filter_proxy.filter_ready is True
        assert widget.live_filter_proxy.filter_scanning is False
        assert widget.frame_table.model() is widget.live_filter_proxy
        assert widget.live_filter_proxy.rowCount() == 10_000
        assert heartbeat_count >= 3

        incoming = [
            CanFrame(
                sequence=20_000 + index,
                timestamp_ns=(20_000 + index) * 1_000,
                arbitration_id=0x100 if index % 2 == 0 else 0x200,
                data=b"\x01",
            )
            for index in range(10_000)
        ]
        widget.frame_model.append_frames(incoming)
        assert widget.live_filter_proxy.rowCount() == 10_000
        assert widget._live_filter_integration._pending_frames
        deadline = monotonic() + 10.0
        while widget.live_filter_proxy.rowCount() < 15_000 and monotonic() < deadline:
            app.processEvents()
            QThreadPool.globalInstance().waitForDone(5)
            sleep(0.001)
        heartbeat_timer.stop()
        assert widget.live_filter_proxy.rowCount() == 15_000
        assert not widget._live_filter_integration._pending_frames

        widget.apply_live_filters.setChecked(False)
        app.processEvents()
        assert widget.frame_table.model() is widget.frame_model
        assert widget.live_filter_proxy.rowCount() == 30_000
        _dispose_widget(app, widget)
        del widget
        collect()

        # During active capture the existing GUI rows are not scanned. Applying the
        # filter clears presentation only and immediately switches to future traffic.
        active_widget = LiveCaptureWidget(
            project,
            controller=_ActiveController(),
            filter_integration_factory=StreamingLiveFilterIntegration,
        )
        active_widget.frame_model.append_frames(frames)
        active_widget.message_model.append_messages([_logical_message(1)])
        active_widget.live_filter_proxy.reload_project_filters()
        active_widget._live_filter_integration.message_proxy.set_filter_set(
            active_widget.live_filter_proxy.filter_set
        )

        active_widget.apply_live_filters.setChecked(True)
        app.processEvents()

        assert active_widget.frame_model.rowCount() == 0
        assert active_widget.message_model.rowCount() == 0
        assert active_widget.live_filter_proxy.filter_ready is True
        assert active_widget.live_filter_proxy.filter_scanning is False
        assert active_widget.frame_table.model() is active_widget.live_filter_proxy
        assert active_widget.live_filter_proxy.rowCount() == 0
        assert active_widget.message_table.model() is active_widget.live_message_filter_proxy
        assert not active_widget._live_filter_integration._frame_tasks

        active_widget.frame_model.append_frames(incoming)
        deadline = monotonic() + 10.0
        while active_widget.live_filter_proxy.rowCount() < 5_000 and monotonic() < deadline:
            app.processEvents()
            QThreadPool.globalInstance().waitForDone(5)
            sleep(0.001)
        assert active_widget.live_filter_proxy.rowCount() == 5_000

        # Temporarily disabling every preset must not discard the user's intent to
        # apply Live filters. Re-enabling a preset in the separate filter window must
        # automatically resume the streaming filter without another checkbox click.
        preset.enabled = False
        repository.save_presets([preset])
        active_widget._live_filter_integration._reload_and_update()
        app.processEvents()

        assert active_widget.apply_live_filters.isChecked()
        assert active_widget.apply_live_filters.isEnabled()
        assert not active_widget.live_filter_proxy.filter_enabled
        assert active_widget.frame_table.model() is active_widget.frame_model
        assert active_widget.frame_model.rowCount() == 0

        preset.enabled = True
        repository.save_presets([preset])
        active_widget._live_filter_integration._reload_and_update()
        app.processEvents()

        assert active_widget.apply_live_filters.isChecked()
        assert active_widget.live_filter_proxy.filter_enabled
        assert active_widget.live_filter_proxy.filter_ready
        assert active_widget.frame_table.model() is active_widget.live_filter_proxy
        assert active_widget.live_filter_proxy.rowCount() == 0

        reactivated = [
            CanFrame(
                sequence=40_000 + index,
                timestamp_ns=(40_000 + index) * 1_000,
                arbitration_id=0x100 if index % 2 == 0 else 0x200,
                data=b"\x02",
            )
            for index in range(20)
        ]
        active_widget.frame_model.append_frames(reactivated)
        deadline = monotonic() + 5.0
        while active_widget.live_filter_proxy.rowCount() < 10 and monotonic() < deadline:
            app.processEvents()
            QThreadPool.globalInstance().waitForDone(5)
            sleep(0.001)
        assert active_widget.live_filter_proxy.rowCount() == 10

        active_widget.apply_live_filters.setChecked(False)
        app.processEvents()
        assert active_widget.frame_table.model() is active_widget.frame_model
        assert active_widget.frame_model.rowCount() == 0
        _dispose_widget(app, active_widget)
        del active_widget
        del repository
        del project
        collect()


if __name__ == "__main__":
    main()
