from __future__ import annotations

import hashlib
import os
import tempfile
from gc import collect
from pathlib import Path
from time import monotonic, sleep

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool, Qt
from PySide6.QtWidgets import QApplication

from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Statistics table")
        session_path = project.live_sessions_dir / "statistics-table.crt.jsonl"
        capture = CaptureSession(
            name="Statistics table session",
            source="test",
            bitrate=250_000,
            channel=0,
        )
        frames = (
            CanFrame(0, 0, 0x100, b"\x01\x02", channel=0),
            CanFrame(1, 1_000_000, 0x18DAF900, b"\x02\x10\x03", channel=1, is_extended_id=True),
            CanFrame(2, 2_000_000, 0x100, b"\x03\x04", channel=0),
            CanFrame(3, 3_000_000, 0x18DAF900, b"\x03\x7F\x10", channel=1, is_extended_id=True),
            CanFrame(4, 4_000_000, 0x100, b"\x05\x06", channel=0),
            CanFrame(5, 5_000_000, 0x200, b"\x07", channel=0),
        )
        with SessionStreamWriter(capture, session_path) as writer:
            for frame in frames:
                writer.append(frame)
        project.register_session(
            session_path,
            name=capture.name,
            source=capture.source,
            status="ready",
        )
        project.finalize_session(
            session_path,
            frame_count=len(frames),
            marker_count=0,
            duration_s=0.005,
        )
        source_hash = _sha256(session_path)

        container = ApplicationContainer()
        widget = container.create_session_view(session_path, project=project)
        widget.tabs.setCurrentIndex(widget.analysis_tab_index)
        widget.run_analysis_button.click()
        _wait_until(app, lambda: widget._analysis_task is None, timeout_s=10.0)

        assert widget.artifact_detail_tabs is not None
        assert widget.artifact_detail_tabs.count() == 2
        assert widget.artifact_detail_tabs.tabText(0) == "Podsumowanie"
        assert widget.artifact_detail_tabs.tabText(1) == "Statystyki CAN ID"
        assert "PODSUMOWANIE SESJI" in widget.artifact_details.toPlainText()

        model = widget.statistics_model
        table = widget.statistics_table
        assert model is not None
        assert table is not None
        assert model.total_rows == 3
        assert model.visible_rows == 3
        assert model.columnCount() == 13
        assert model.channels == (0, 1)
        assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "0x100"
        assert model.data(model.index(0, 4), Qt.ItemDataRole.DisplayRole) == "3"
        assert "3 z 3" in widget.statistics_status.text()

        widget.statistics_filter.setText("18DAF900")
        app.processEvents()
        assert model.visible_rows == 1
        assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "0x18DAF900"
        assert model.data(model.index(0, 2), Qt.ItemDataRole.DisplayRole) == "EXT"
        assert "1 z 3" in widget.statistics_status.text()

        widget.statistics_filter.clear()
        channel_index = widget.statistics_channel.findData(1)
        assert channel_index > 0
        widget.statistics_channel.setCurrentIndex(channel_index)
        app.processEvents()
        assert model.visible_rows == 1
        assert model.row_at(0).channel == 1

        widget.statistics_channel.setCurrentIndex(0)
        table.sortByColumn(9, Qt.SortOrder.DescendingOrder)
        app.processEvents()
        assert model.visible_rows == 3
        assert model.row_at(0).frequency_hz is not None
        assert _sha256(session_path) == source_hash

        _dispose_widget(app, widget)
        del widget
        collect()

        reopened = container.create_session_view(session_path, project=project)
        assert reopened.artifact_table.rowCount() == 1
        assert reopened.statistics_model.total_rows == 3
        assert reopened.artifact_detail_tabs.tabText(0) == "Podsumowanie"
        assert reopened.artifact_detail_tabs.tabText(1) == "Statystyki CAN ID"
        assert "PODSUMOWANIE SESJI" in reopened.artifact_details.toPlainText()
        assert _sha256(session_path) == source_hash
        _dispose_widget(app, reopened)
        del reopened
        del project
        collect()
    return 0


def _wait_until(app: QApplication, predicate, *, timeout_s: float) -> None:
    deadline = monotonic() + timeout_s
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("timed out waiting for session statistics")
        app.processEvents()
        sleep(0.01)
    QThreadPool.globalInstance().waitForDone(5_000)
    app.processEvents()


def _dispose_widget(app: QApplication, widget) -> None:
    widget.shutdown()
    QThreadPool.globalInstance().waitForDone(5_000)
    widget.close()
    app.processEvents()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
