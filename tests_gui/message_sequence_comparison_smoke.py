from __future__ import annotations

import gc
import os
from tempfile import TemporaryDirectory
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.extensions import MESSAGE_SEQUENCE_PROVIDER_ID
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.comparison_sets_analysis_view import (
    configure_comparison_analysis_window,
)
from gui.message_sequence_analysis_dialog import (
    MessageSequenceComparisonAnalysisDialog,
)


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTMessageSequenceComparisonSmoke")
    settings = QSettings()
    settings.clear()

    with TemporaryDirectory() as temporary:
        os.environ["CRT_APP_DATA_DIR"] = f"{temporary}/app-data"
        project = CrtProject.create(
            f"{temporary}/project",
            name="Message sequence GUI",
        )
        before = _create_session(project, "before", _before_frames())
        after = _create_session(project, "after", _after_frames())
        comparison = ComparisonSetStore(project).create(
            name="Sequence before versus after",
            session_ids=(before.id, after.id),
            base_session_id=before.id,
        )

        dialog = MessageSequenceComparisonAnalysisDialog(
            project,
            comparison.id,
        )
        configure_comparison_analysis_window(dialog)
        provider_index = dialog.provider_combo.findData(
            MESSAGE_SEQUENCE_PROVIDER_ID
        )
        assert provider_index >= 0
        dialog.provider_combo.setCurrentIndex(provider_index)
        dialog.show()
        app.processEvents()

        dialog.run_button.click()
        _wait_for_analysis(app, dialog)

        assert dialog.artifact_combo.count() == 1
        assert dialog.sessions_table.rowCount() == 2
        assert dialog.sessions_table.columnCount() == 10
        assert dialog.changes_table.rowCount() >= 1
        assert dialog.changes_table.columnCount() == 12
        assert "Unikalne sekwencje" in dialog.summary_label.text()
        assert "Macierz kompletna: tak" in dialog.summary_label.text()
        assert "zakończone" in dialog.status_label.text().casefold()

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
    print("Message sequence comparison GUI smoke: OK")


def _wait_for_analysis(
    app: QApplication,
    dialog: MessageSequenceComparisonAnalysisDialog,
) -> None:
    deadline = monotonic() + 15.0
    while dialog._task is not None:
        QThreadPool.globalInstance().waitForDone(50)
        app.sendPostedEvents()
        app.processEvents()
        if monotonic() > deadline:
            raise TimeoutError("message sequence comparison did not finish")


def _before_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100),
        _frame(1, 10, 0x100),
        _frame(2, 20, 0x200),
        _frame(3, 30, 0x100),
        _frame(4, 50, 0x300),
    ]


def _after_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100),
        _frame(1, 5, 0x200),
        _frame(2, 15, 0x300),
        _frame(3, 30, 0x100),
        _frame(4, 45, 0x300),
    ]


def _frame(
    sequence: int,
    timestamp_ns: int,
    arbitration_id: int,
) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=arbitration_id,
        data=bytes((sequence & 0xFF,)),
        channel=0,
        is_extended_id=False,
    )


def _create_session(
    project: CrtProject,
    name: str,
    frames: list[CanFrame],
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(
        name=name,
        source="test",
        bitrate=250_000,
        channel=0,
    )
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True})
    record = project.register_session(
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
            max(frame.timestamp_ns for frame in frames)
            / 1_000_000_000.0
        ),
    )
    return project.session_by_path(path) or record


if __name__ == "__main__":
    main()
