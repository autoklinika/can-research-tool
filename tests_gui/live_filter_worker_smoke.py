from __future__ import annotations

from tempfile import TemporaryDirectory
from time import monotonic, sleep

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QApplication

from app.filters import FilterMode, FilterPreset, ProjectFilterRepository
from app.models import CanFrame
from app.project import CrtProject
from gui.live_capture import LiveCaptureWidget


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
        ProjectFilterRepository(project.database_path).save_presets([preset])

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

        # Reload the saved preset and enable filtering. Full predicate evaluation
        # is scheduled in QThreadPool; the proxy shows the raw buffer until ready.
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

        # New rows are queued immediately and evaluated by a separate worker.
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
        widget.close()

    app.processEvents()


if __name__ == "__main__":
    main()
