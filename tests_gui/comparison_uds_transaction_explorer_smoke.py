from __future__ import annotations

import gc
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.comparison_visualization_stage2d1 import ComparisonVisualizationDialog

REQUEST_ID = 0x18DA30F9
RESPONSE_ID = 0x18DAF930
REQUEST_KEY = "0:EXT:18DA30F9:data"
RESPONSE_KEY = "0:EXT:18DAF930:data"


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTComparisonUdsExplorerStage2D1Smoke")
    settings = QSettings()
    settings.clear()

    with TemporaryDirectory() as temporary:
        os.environ["CRT_APP_DATA_DIR"] = f"{temporary}/app-data"
        project = CrtProject.create(
            f"{temporary}/project",
            name="UDS explorer smoke",
        )
        before = _create_session(
            project,
            "before",
            [
                _frame(0, 0, REQUEST_ID, _sf(b"\x22\xF1\x90")),
                _frame(1, 10_000_000, RESPONSE_ID, _sf(b"\x7F\x22\x78")),
                _frame(
                    2,
                    40_000_000,
                    RESPONSE_ID,
                    _sf(b"\x62\xF1\x90\x12"),
                ),
            ],
        )
        after = _create_session(
            project,
            "after",
            [
                _frame(0, 0, REQUEST_ID, _sf(b"\x22\xF1\x90")),
                _frame(
                    1,
                    70_000_000,
                    RESPONSE_ID,
                    _sf(b"\x62\xF1\x90\x34"),
                ),
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

        explorer_index = dialog.result_tabs.indexOf(dialog.uds_explorer)
        assert explorer_index >= 0
        assert dialog.result_tabs.tabText(explorer_index) == "Transakcje UDS"

        dialog.uds_latency.request_key_edit.setText(REQUEST_KEY)
        dialog.uds_latency.response_key_edit.setText(RESPONSE_KEY)
        dialog.uds_latency.timeout_spin.setValue(1_000.0)
        dialog.uds_latency.analyze_button.click()
        _wait_for_idle(app, dialog)
        artifact_id = dialog.uds_latency._loaded_artifact_id
        assert artifact_id

        dialog.result_tabs.setCurrentIndex(explorer_index)
        dialog.uds_explorer.load_button.click()
        _wait_for_idle(app, dialog)
        explorer = dialog.uds_explorer
        assert explorer._source_artifact_id == artifact_id
        assert explorer._explorer_result is not None
        assert explorer.transaction_table.rowCount() == 2
        assert explorer.group_table.rowCount() >= 2
        assert explorer.comparison_table.rowCount() >= 1
        assert "bez ponownego skanowania" in explorer.status_label.text()

        opened: list[tuple[str, int, str]] = []
        dialog.source_row_open_requested.connect(
            lambda session_id, source_row, message_key, _dialog: opened.append(
                (session_id, source_row, message_key)
            )
        )
        explorer.transaction_table.selectRow(0)
        _drain(app)
        assert "DID 0xF190" in explorer.details.toPlainText()
        assert "7F 22 78" in explorer.details.toPlainText()
        assert "62 F1 90 12" in explorer.details.toPlainText()

        explorer.open_request_button.click()
        _drain(app)
        assert opened[-1] == (before.id, 0, REQUEST_KEY)
        assert not explorer.isEnabled()
        dialog.evidence_navigation_succeeded()
        assert explorer.isEnabled()

        explorer.transaction_table.selectRow(0)
        _drain(app)
        explorer.open_first_button.click()
        _drain(app)
        assert opened[-1] == (before.id, 1, RESPONSE_KEY)
        dialog.evidence_navigation_succeeded()

        explorer.transaction_table.selectRow(0)
        _drain(app)
        explorer.open_final_button.click()
        _drain(app)
        assert opened[-1] == (before.id, 2, RESPONSE_KEY)
        dialog.evidence_navigation_succeeded()

        grouping_index = explorer.grouping_combo.findData("did")
        assert grouping_index >= 0
        explorer.grouping_combo.setCurrentIndex(grouping_index)
        explorer.apply_button.click()
        _drain(app)
        assert any(
            "DID 0xF190"
            in explorer.group_table.item(row, 1).text()
            for row in range(explorer.group_table.rowCount())
        )

        explorer.search_edit.setText("34")
        explorer.apply_button.click()
        _drain(app)
        assert explorer.transaction_table.rowCount() == 1
        explorer.transaction_table.selectRow(0)
        _drain(app)
        assert "62 F1 90 34" in explorer.details.toPlainText()

        transactions_csv = Path(temporary) / "transactions.csv"
        groups_csv = Path(temporary) / "groups.csv"
        assert explorer.export_transactions(transactions_csv) == transactions_csv
        assert explorer.export_groups(groups_csv) == groups_csv
        assert "session_id;session_name" in transactions_csv.read_text(
            encoding="utf-8-sig"
        )
        assert "grouping_mode;group_key" in groups_csv.read_text(
            encoding="utf-8-sig"
        )

        dialog.close()
        _drain(app)
        dialog.deleteLater()
        _drain(app)

        restored = ComparisonVisualizationDialog(project, comparison.id)
        restored.show()
        _drain(app)
        _wait_for_idle(app, restored)
        assert restored.uds_explorer._source_artifact_id == artifact_id
        assert restored.uds_explorer._explorer_result is not None
        assert restored.uds_explorer.transaction_table.rowCount() == 2
        assert (
            "bez ponownego skanowania"
            in restored.uds_explorer.status_label.text()
        )

        restored.close()
        restored.deleteLater()
        _drain(app)
        assert QThreadPool.globalInstance().waitForDone(5_000)
        restored = None
        dialog = None
        project = None
        gc.collect()

    settings.clear()
    os.environ.pop("CRT_APP_DATA_DIR", None)
    print("Comparison UDS transaction explorer Stage 2D1 smoke: OK")


def _wait_for_idle(
    app: QApplication,
    dialog: ComparisonVisualizationDialog,
) -> None:
    deadline = monotonic() + 45.0
    while monotonic() < deadline:
        _drain(app)
        if not dialog.uds_latency._tasks and not dialog.uds_explorer._tasks:
            return
        QThreadPool.globalInstance().waitForDone(50)
    raise TimeoutError("UDS transaction explorer did not become idle")


def _drain(app: QApplication) -> None:
    app.sendPostedEvents()
    app.processEvents()


def _create_session(
    project: CrtProject,
    name: str,
    frames: list[CanFrame],
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    writer = SessionStreamWriter(
        CaptureSession(
            name=name,
            source="test",
            bitrate=250_000,
            channel=0,
        ),
        path,
    )
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True})
    project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=(
            (frames[-1].timestamp_ns - frames[0].timestamp_ns)
            / 1_000_000_000.0
            if len(frames) > 1
            else 0.0
        ),
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(f"session was not registered: {path}")
    return record


def _frame(
    sequence: int,
    timestamp_ns: int,
    arbitration_id: int,
    data: bytes,
) -> CanFrame:
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
