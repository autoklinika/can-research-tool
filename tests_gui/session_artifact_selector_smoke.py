from __future__ import annotations

import hashlib
import os
import tempfile
from gc import collect
from pathlib import Path
from time import monotonic, sleep

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication

from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Artifact selector")
        session_path = project.live_sessions_dir / "artifact-selector.crt.jsonl"
        capture = CaptureSession(
            name="Artifact selector session",
            source="test",
            bitrate=250_000,
            channel=0,
        )
        with SessionStreamWriter(capture, session_path) as writer:
            for sequence in range(8):
                writer.append(
                    CanFrame(
                        sequence=sequence,
                        timestamp_ns=sequence * 1_000_000,
                        arbitration_id=0x100 + (sequence % 2),
                        data=bytes((sequence, 0xAA)),
                        channel=0,
                    )
                )
        project.register_session(
            session_path,
            name=capture.name,
            source=capture.source,
            status="ready",
        )
        project.finalize_session(
            session_path,
            frame_count=8,
            marker_count=0,
            duration_s=0.007,
        )
        source_hash = _sha256(session_path)

        widget = ApplicationContainer().create_session_view(session_path, project=project)
        widget.tabs.setCurrentIndex(widget.analysis_tab_index)
        assert widget.artifact_table is None
        assert widget.artifact_selector.count() == 1
        assert not widget.artifact_selector.isEnabled()

        widget.run_analysis_button.click()
        _wait_until(app, lambda: widget._analysis_task is None, timeout_s=10.0)
        first_artifact_id = str(widget.artifact_selector.currentData())
        assert first_artifact_id
        assert widget.artifact_selector.count() == 1

        widget.run_analysis_button.click()
        _wait_until(app, lambda: widget._analysis_task is None, timeout_s=10.0)
        second_artifact_id = str(widget.artifact_selector.currentData())
        assert second_artifact_id
        assert second_artifact_id != first_artifact_id
        assert widget.artifact_selector.count() == 2
        assert "Statystyki sesji" in widget.artifact_selector.currentText()
        assert "wersja 1.0.0" in widget.artifact_summary_line.text()
        assert widget.artifact_details.isHidden()

        current_index = widget.artifact_selector.currentIndex()
        other_index = 1 if current_index == 0 else 0
        other_artifact_id = str(widget.artifact_selector.itemData(other_index))
        widget.artifact_selector.setCurrentIndex(other_index)
        app.processEvents()
        assert str(widget.artifact_selector.currentData()) == other_artifact_id
        widget.artifact_info_toggle.click()
        app.processEvents()
        assert not widget.artifact_details.isHidden()
        technical = widget.artifact_details.toPlainText()
        assert f"ID: {other_artifact_id}" in technical
        assert "Provider: crt.analysis.session_statistics" in technical
        assert "Schemat: 1" in technical
        assert "session-statistics.json" in technical
        assert _sha256(session_path) == source_hash

        widget.artifact_info_toggle.click()
        app.processEvents()
        assert widget.artifact_details.isHidden()
        _dispose_widget(app, widget)
        del widget
        del project
        collect()
    return 0


def _wait_until(app: QApplication, predicate, *, timeout_s: float) -> None:
    deadline = monotonic() + timeout_s
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("timed out waiting for artifact analysis")
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
