from __future__ import annotations

from tempfile import TemporaryDirectory
from time import monotonic

from PySide6.QtCore import QThreadPool
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
        widget.apply_live_filters.setChecked(True)
        assert widget.frame_table.model() is widget.frame_model
        assert widget.live_filter_proxy.filter_scanning is True

        deadline = monotonic() + 10.0
        while not widget.live_filter_proxy.filter_ready and monotonic() < deadline:
            app.processEvents()
            QThreadPool.globalInstance().waitForDone(20)

        app.processEvents()
        assert widget.live_filter_proxy.filter_ready is True
        assert widget.live_filter_proxy.filter_scanning is False
        assert widget.frame_table.model() is widget.live_filter_proxy
        assert widget.live_filter_proxy.rowCount() == 10_000

        # New rows after the worker snapshot are evaluated incrementally.
        widget.frame_model.append_frames(
            [
                CanFrame(
                    sequence=20_000,
                    timestamp_ns=20_000_000,
                    arbitration_id=0x100,
                    data=b"\x01",
                ),
                CanFrame(
                    sequence=20_001,
                    timestamp_ns=20_001_000,
                    arbitration_id=0x200,
                    data=b"\x02",
                ),
            ]
        )
        app.processEvents()
        assert widget.live_filter_proxy.rowCount() == 10_001

        widget.apply_live_filters.setChecked(False)
        app.processEvents()
        assert widget.frame_table.model() is widget.frame_model
        assert widget.live_filter_proxy.rowCount() == 20_002
        widget.close()

    app.processEvents()


if __name__ == "__main__":
    main()
