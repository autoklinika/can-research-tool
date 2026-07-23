from __future__ import annotations

import hashlib
import os
import tempfile
from gc import collect
from pathlib import Path
from time import monotonic, sleep

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication, QProgressBar

from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer
from gui.session_statistics_visual_summary import ShareBarDelegate


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Visual summary")
        session_path = project.live_sessions_dir / "visual-summary.crt.jsonl"
        capture = CaptureSession(
            name="Visual summary session",
            source="test",
            bitrate=250_000,
            channel=0,
        )
        frames = (
            CanFrame(0, 0, 0x100, b"\x01\x02", channel=0),
            CanFrame(
                1,
                1_000_000,
                0x18DAF900,
                b"\x02\x10\x03",
                channel=1,
                is_extended_id=True,
            ),
            CanFrame(2, 2_000_000, 0x100, b"\x03\x04", channel=0),
            CanFrame(
                3,
                3_000_000,
                0x18DAF900,
                b"\x03\x7F\x10",
                channel=1,
                is_extended_id=True,
            ),
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

        assert widget.artifact_table is None
        assert widget.artifact_selector.count() == 1
        assert widget.statistics_visual_page is not None
        assert widget.statistics_visual_page.objectName() == "sessionStatisticsVisualSummaryPage"
        assert widget.artifact_detail_tabs.tabText(0) == "Podsumowanie"
        assert widget.artifact_detail_tabs.tabText(1) == "Statystyki CAN ID"
        assert "Statystyki sesji" in widget.artifact_summary_line.text()
        assert widget.artifact_details.isHidden()

        cards = widget.statistics_kpi_cards
        assert set(cards) == {"frames", "ids", "duration", "frequency", "anomalies"}
        assert cards["frames"].value_label.text() == "6"
        assert cards["ids"].value_label.text() == "3"
        assert cards["duration"].value_label.text() == "0.005 s"
        assert cards["frequency"].value_label.text() == "1000.000 Hz"
        assert cards["anomalies"].value_label.text() == "0"
        assert cards["anomalies"].hint_label.text() == "zero 0 · ujemne 0"

        top_table = widget.statistics_top_table
        assert top_table is not None
        assert top_table.rowCount() == 3
        assert top_table.item(0, 0).text().startswith("0x100 · CH0 · DATA · STD")
        assert top_table.item(0, 1).text() == "3"
        share_bar = top_table.cellWidget(0, 2)
        assert isinstance(share_bar, QProgressBar)
        assert share_bar.value() == 5000
        assert share_bar.format() == "50.00%"

        delegate = widget.statistics_table.itemDelegateForColumn(5)
        assert isinstance(delegate, ShareBarDelegate)
        assert delegate is widget.statistics_share_delegate
        widget.artifact_info_toggle.click()
        app.processEvents()
        assert not widget.artifact_details.isHidden()
        assert "INFORMACJE O ARTEFAKCIE" in widget.artifact_details.toPlainText()
        assert _sha256(session_path) == source_hash

        _dispose_widget(app, widget)
        del widget
        collect()

        reopened = container.create_session_view(session_path, project=project)
        assert reopened.artifact_table is None
        assert reopened.artifact_selector.count() == 1
        assert reopened.statistics_top_table.rowCount() == 3
        assert reopened.statistics_kpi_cards["frames"].value_label.text() == "6"
        assert reopened.statistics_kpi_cards["ids"].value_label.text() == "3"
        assert "Statystyki sesji" in reopened.artifact_summary_line.text()
        assert reopened.artifact_details.isHidden()
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
            raise AssertionError("timed out waiting for visual statistics summary")
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
