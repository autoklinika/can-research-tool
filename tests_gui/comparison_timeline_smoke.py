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
from gui.application_container import ApplicationContainer
from gui.comparison_sets_analysis_view import AnalysisEnabledComparisonSetsView
from gui.comparison_visualization_hardened import ComparisonVisualizationDialog
from gui.project_navigator import ProjectNavigator


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

        window = ApplicationContainer().create_main_window()
        window.show()
        window._set_project(project)
        window._open_comparison_sets(comparison.id)
        app.processEvents()

        comparison_view = window.navigator.widget("comparison-sets")
        assert isinstance(comparison_view, AnalysisEnabledComparisonSetsView)
        assert comparison_view.select_comparison_set(comparison.id)
        comparison_view._open_analysis()
        app.processEvents()
        dialog = comparison_view._analysis_dialogs.get(comparison.id)
        assert isinstance(dialog, ComparisonVisualizationDialog)

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

        stale_generation = dialog.timeline._generation
        dialog.timeline.canvas.set_result(None)
        dialog.timeline.cancel()
        dialog.timeline._timeline_ready(stale_generation, result)
        assert dialog.timeline.canvas._result is None

        dialog.timeline.mode_combo.setCurrentIndex(
            dialog.timeline.mode_combo.findData(SYNC_MESSAGE_KEY)
        )
        dialog.timeline.anchor_edit.setText("0:STD:200:data")
        dialog.timeline.build_button.click()
        _wait_for_timeline(app, dialog)
        result = dialog.timeline.canvas._result
        assert result is not None
        assert [lane.anchor_source_row for lane in result.lanes] == [1, 1]

        event = result.lanes[0].events[-1]
        assert event.source_row == 2
        dialog.timeline._event_selected(event)
        dialog.timeline.open_button.click()

        session_path = project.absolute_path(before.relative_path)
        session_key = ProjectNavigator.session_key(session_path)
        deadline = monotonic() + 20.0
        session_view = None
        while monotonic() < deadline:
            QThreadPool.globalInstance().waitForDone(50)
            app.sendPostedEvents()
            app.processEvents()
            session_view = window.navigator.widget(session_key)
            if (
                session_view is not None
                and session_view.frame_table.currentIndex().row() == event.source_row
            ):
                break
        assert session_view is not None
        assert window.tabs.currentWidget() is session_view
        assert session_view.frame_table.currentIndex().row() == event.source_row
        assert "0x300" in session_view.frame_table.model().data(
            session_view.frame_table.model().index(event.source_row, 2)
        )

        dialog.timeline._event_selected(event)
        assert dialog.timeline.open_button.isEnabled()
        dialog.timeline._timeline_failed(dialog.timeline._generation, "test failure")
        assert dialog.timeline._selected_event is None
        assert not dialog.timeline.open_button.isEnabled()

        assert QThreadPool.globalInstance().waitForDone(5_000)
        window.navigator.close_all()
        window.close()
        window.deleteLater()
        app.sendPostedEvents()
        app.processEvents()

        session_view = None
        dialog = None
        comparison_view = None
        window = None
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
