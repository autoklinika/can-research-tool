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
from app.session_analysis_service import SessionAnalysisService
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Minimal analysis chrome")
        session_path = project.live_sessions_dir / "minimal-analysis.crt.jsonl"
        capture = CaptureSession(
            name="Minimal analysis chrome session",
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

        assert widget.analysis_progress.isHidden()
        assert widget.analysis_status.isHidden()
        assert widget.artifact_selector_bar is not None
        assert widget.artifact_selector_bar.isHidden()
        assert widget.artifact_summary_line.isHidden()

        widget.run_analysis_button.click()
        assert widget._analysis_task is not None
        assert not widget.analysis_progress.isHidden()
        assert not widget.analysis_status.isHidden()
        _wait_until(app, lambda: widget._analysis_task is None, timeout_s=10.0)

        assert widget.analysis_progress.isHidden()
        assert widget.analysis_status.isHidden()
        assert widget.artifact_selector.count() == 1
        assert widget.artifact_selector_bar.isHidden()
        assert widget.statistics_kpi_cards["frames"].value_label.text() == "8"

        widget.run_analysis_button.click()
        assert widget._analysis_task is not None
        assert not widget.analysis_progress.isHidden()
        assert not widget.analysis_status.isHidden()
        _wait_until(app, lambda: widget._analysis_task is None, timeout_s=10.0)

        assert widget.analysis_progress.isHidden()
        assert widget.analysis_status.isHidden()
        assert widget.artifact_selector.count() == 2
        assert not widget.artifact_selector_bar.isHidden()
        assert widget.artifact_summary_line.isHidden()
        assert _sha256(session_path) == source_hash

        _dispose_widget(app, widget)
        del widget

        original_list_artifacts = SessionAnalysisService.list_artifacts
        error_widget = None

        def fail_list_artifacts(_service, _session_id):
            raise OSError("simulated artifact catalog read failure")

        SessionAnalysisService.list_artifacts = fail_list_artifacts
        try:
            error_widget = ApplicationContainer().create_session_view(
                session_path,
                project=project,
            )
            error_widget.tabs.setCurrentIndex(error_widget.analysis_tab_index)
            assert error_widget.analysis_progress.isHidden()
            assert not error_widget.analysis_status.isHidden()
            assert error_widget.analysis_status.text().startswith("Nie można odczytać")
        finally:
            SessionAnalysisService.list_artifacts = original_list_artifacts
            if error_widget is not None:
                _dispose_widget(app, error_widget)

        del error_widget
        del project
        collect()
    return 0


def _wait_until(app: QApplication, predicate, *, timeout_s: float) -> None:
    deadline = monotonic() + timeout_s
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("timed out waiting for minimal analysis chrome")
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
