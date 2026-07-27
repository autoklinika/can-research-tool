from __future__ import annotations

import gc
import os
from tempfile import TemporaryDirectory
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.comparison_timeline import SYNC_MESSAGE_KEY
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.comparison_visualization_hardened import ComparisonVisualizationDialog


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTComparisonTimelineSmoke")
    settings = QSettings()
    settings.clear()

    with TemporaryDirectory() as temporary:
        os.environ["CRT_APP_DATA_DIR"] = f"{temporary}/app-data"
        project = CrtProject.create(f"{temporary}/project", name="Timeline smoke")
        before = _create_session(project, "before", 0)
        after = _create_session(project, "after", 100_000_000)
        comparison = ComparisonSetStore(project).create(
            name="Before versus after",
            session_ids=(before.id, after.id),
            base_session_id=before.id,
        )

        dialog = ComparisonVisualizationDialog(project, comparison.id)
        dialog.show()
        app.processEvents()

        timeline_index = dialog.result_tabs.indexOf(dialog.timeline)
        assert timeline_index >= 0
        assert dialog.result_tabs.tabText(timeline_index) == "Oś czasu"
        dialog.result_tabs.setCurrentIndex(timeline_index)

        dialog.timeline.build_button.click()
        _wait_for_timeline(app, dialog)
        result = dialog.timeline.canvas._result
        assert result is not None
        assert len(result.lanes) == 2
        assert all(lane.anchor_source_row == 0 for lane in result.lanes)

        dialog.timeline.mode_combo.setCurrentIndex(
            dialog.timeline.mode_combo.findData(SYNC_MESSAGE_KEY)
        )
        dialog.timeline.anchor_edit.setText("0:STD:200:data")
        dialog.timeline.build_button.click()
        _wait_for_timeline(app, dialog)
        result = dialog.timeline.canvas._result
        assert result is not None
        assert [lane.anchor_source_row for lane in result.lanes] == [1, 1]

        emitted: list[tuple] = []
        dialog.source_row_open_requested.connect(
            lambda *args: emitted.append(tuple(args))
        )
        event = result.lanes[0].events[0]
        dialog.timeline._event_selected(event)
        dialog.timeline.open_button.click()
        app.processEvents()
        assert emitted
        assert emitted[0][0] == before.id
        assert emitted[0][1] == event.source_row
        assert emitted[0][2] == event.message_key
        assert emitted[0][3] is dialog

        dialog.close()
        dialog.deleteLater()
        assert QThreadPool.globalInstance().waitForDone(5_000)
        app.sendPostedEvents()
        app.processEvents()

        dialog = None
        project = None
        gc.collect()

    settings.clear()
    os.environ.pop("CRT_APP_DATA_DIR", None)
    print("Comparison timeline smoke: OK")


def _wait_for_timeline(
    app: QApplication,
    dialog: ComparisonVisualizationDialog,
) -> None:
    deadline = monotonic() + 30.0
    while dialog.timeline._tasks:
        QThreadPool.globalInstance().waitForDone(50)
        app.sendPostedEvents()
        app.processEvents()
        if monotonic() > deadline:
            raise TimeoutError("comparison timeline did not become idle")


def _create_session(project: CrtProject, name: str, offset_ns: int):
    frames = [
        _frame(0, offset_ns, 0x100),
        _frame(1, offset_ns + 10_000_000, 0x200),
        _frame(2, offset_ns + 20_000_000, 0x300),
    ]
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    writer = SessionStreamWriter(
        CaptureSession(name=name, source="test", bitrate=250_000, channel=0),
        path,
    )
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True})
    project.register_session(path, name=name, source="test", status="ready")
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=0.02,
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(f"session was not registered: {path}")
    return record


def _frame(sequence: int, timestamp_ns: int, arbitration_id: int) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=arbitration_id,
        data=bytes([sequence]),
        channel=0,
    )


if __name__ == "__main__":
    main()
