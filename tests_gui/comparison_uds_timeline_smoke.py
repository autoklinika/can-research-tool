from __future__ import annotations

import gc
import os
from tempfile import TemporaryDirectory
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.comparison_visualization_stage2d2 import ComparisonVisualizationDialog


REQUEST_ID = 0x18DA30F9
RESPONSE_ID = 0x18DAF930
REQUEST_KEY = "0:EXT:18DA30F9:data"
RESPONSE_KEY = "0:EXT:18DAF930:data"


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTComparisonUdsTimelineStage2D2Smoke")
    QSettings().clear()

    with TemporaryDirectory() as temporary:
        os.environ["CRT_APP_DATA_DIR"] = f"{temporary}/app-data"
        project = CrtProject.create(f"{temporary}/project", name="UDS timeline smoke")
        before = _create_session(
            project,
            "before",
            [
                _frame(0, 0, REQUEST_ID, _sf(b"\x22\xF1\x90")),
                _frame(1, 10_000_000, RESPONSE_ID, _sf(b"\x7F\x22\x78")),
                _frame(2, 40_000_000, RESPONSE_ID, _sf(b"\x62\xF1\x90\x12")),
                _frame(3, 100_000_000, REQUEST_ID, _sf(b"\x31\x01\xF0\x22")),
                _frame(4, 130_000_000, RESPONSE_ID, _sf(b"\x71\x01\xF0\x22")),
                _frame(5, 250_000_000, 0x18FF0001, b"\x00"),
            ],
        )
        after = _create_session(
            project,
            "after",
            [
                _frame(0, 1_000_000_000, REQUEST_ID, _sf(b"\x31\x01\xF0\x22")),
                _frame(1, 1_030_000_000, RESPONSE_ID, _sf(b"\x71\x01\xF0\x22")),
                _frame(2, 1_100_000_000, REQUEST_ID, _sf(b"\x22\xF1\x90")),
                _frame(3, 1_140_000_000, RESPONSE_ID, _sf(b"\x7F\x22\x31")),
                _frame(4, 1_180_000_000, REQUEST_ID, _sf(b"\x19\x02\xFF")),
                _frame(5, 1_400_000_000, 0x18FF0001, b"\x00"),
            ],
        )
        comparison = ComparisonSetStore(project).create(
            name="Before versus after",
            session_ids=(before.id, after.id),
            base_session_id=before.id,
        )

        dialog = ComparisonVisualizationDialog(project, comparison.id)
        dialog.show()
        _drain(app)
        _wait_for_idle(app, dialog)

        dialog.timeline.build_button.click()
        _wait_for_idle(app, dialog)
        assert dialog.timeline._current_result is not None
        dialog.timeline.save_button.click()
        _wait_for_idle(app, dialog)
        alignment_id = dialog.timeline._loaded_artifact_id
        assert alignment_id

        dialog.uds_latency.request_key_edit.setText(REQUEST_KEY)
        dialog.uds_latency.response_key_edit.setText(RESPONSE_KEY)
        dialog.uds_latency.timeout_spin.setValue(50.0)
        dialog.uds_latency.analyze_button.click()
        _wait_for_idle(app, dialog)
        uds_artifact_id = dialog.uds_latency._loaded_artifact_id
        assert uds_artifact_id

        uds_timeline_index = dialog.result_tabs.indexOf(dialog.uds_timeline)
        assert uds_timeline_index >= 0
        assert dialog.result_tabs.tabText(uds_timeline_index) == "Oś UDS"
        dialog.result_tabs.setCurrentIndex(uds_timeline_index)
        dialog.uds_timeline.load_button.click()
        _wait_for_idle(app, dialog)

        view = dialog.uds_timeline
        result = view._result
        assert result is not None
        assert result.alignment_artifact_id == alignment_id
        assert result.uds_artifact_id == uds_artifact_id
        assert result.visible_transaction_count == 5
        assert view.transaction_table.rowCount() == 5
        assert view.difference_table.rowCount() == 1
        assert view.difference_table.item(0, 2).text() == "1"
        assert view.difference_table.item(0, 3).text() == "2"
        assert "bez skanowania sesji" in view.status_label.text()

        opened: list[tuple[str, int, str]] = []
        dialog.source_row_open_requested.connect(
            lambda session_id, source_row, message_key, _dialog: opened.append(
                (session_id, source_row, message_key)
            )
        )
        view.transaction_table.selectRow(0)
        _drain(app)
        assert "DID 0xF190" in view.details.text()
        assert "ResponsePending 0x78: 1" in view.details.text()
        view.open_request_button.click()
        _drain(app)
        assert opened[-1] == (before.id, 0, REQUEST_KEY)
        assert not view.isEnabled()
        dialog.evidence_navigation_succeeded()
        assert view.isEnabled()

        view.transaction_table.selectRow(0)
        _drain(app)
        view.open_first_button.click()
        _drain(app)
        assert opened[-1] == (before.id, 1, RESPONSE_KEY)
        dialog.evidence_navigation_succeeded()

        view.transaction_table.selectRow(0)
        _drain(app)
        view.open_final_button.click()
        _drain(app)
        assert opened[-1] == (before.id, 2, RESPONSE_KEY)
        dialog.evidence_navigation_succeeded()

        view.did_edit.setText("F190")
        view.apply_button.click()
        _drain(app)
        assert view.transaction_table.rowCount() == 2
        assert all(
            "DID 0xF190" in view.transaction_table.item(row, 3).text()
            for row in range(view.transaction_table.rowCount())
        )

        view.clear_button.click()
        _drain(app)
        assert view.transaction_table.rowCount() == 5
        timeout_index = view.status_combo.findData("timeout")
        assert timeout_index >= 0
        view.status_combo.setCurrentIndex(timeout_index)
        view.apply_button.click()
        _drain(app)
        assert view.transaction_table.rowCount() == 1
        assert "Timeout" in view.transaction_table.item(0, 4).text()

        dialog.close()
        dialog.deleteLater()
        _drain(app)
        assert QThreadPool.globalInstance().waitForDone(5_000)
        dialog = None
        project = None
        gc.collect()

    QSettings().clear()
    os.environ.pop("CRT_APP_DATA_DIR", None)
    print("Comparison UDS timeline Stage 2D2 smoke: OK")


def _wait_for_idle(app: QApplication, dialog: ComparisonVisualizationDialog) -> None:
    deadline = monotonic() + 60.0
    while monotonic() < deadline:
        _drain(app)
        tasks = (
            bool(dialog.timeline._tasks)
            or bool(dialog.timeline._storage_tasks)
            or bool(dialog.uds_latency._tasks)
            or bool(dialog.uds_explorer._tasks)
            or bool(dialog.uds_timeline._tasks)
        )
        if not tasks:
            return
        QThreadPool.globalInstance().waitForDone(50)
    raise TimeoutError("Stage 2D2 comparison dialog did not become idle")


def _drain(app: QApplication) -> None:
    app.sendPostedEvents()
    app.processEvents()


def _create_session(project: CrtProject, name: str, frames: list[CanFrame]):
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
        duration_s=(frames[-1].timestamp_ns - frames[0].timestamp_ns) / 1_000_000_000.0,
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(f"session was not registered: {path}")
    return record


def _frame(sequence: int, timestamp_ns: int, arbitration_id: int, data: bytes) -> CanFrame:
    return CanFrame(
        sequence,
        timestamp_ns,
        arbitration_id,
        data,
        channel=0,
        is_extended_id=True,
    )


def _sf(payload: bytes) -> bytes:
    return bytes([len(payload)]) + payload


if __name__ == "__main__":
    main()
