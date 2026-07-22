from __future__ import annotations

import hashlib
import os
import tempfile
from gc import collect
from pathlib import Path
from time import monotonic, sleep

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication, QTabWidget

from app.extensions.builtin import SESSION_STATISTICS_PROVIDER_ID
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer
from gui.project_navigator import CloseTabResult


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Analysis GUI")
        session_path = project.live_sessions_dir / "analysis.crt.jsonl"
        capture = CaptureSession(
            name="Analysis GUI session",
            source="test",
            bitrate=250_000,
            channel=0,
        )
        with SessionStreamWriter(capture, session_path) as writer:
            for sequence in range(12):
                writer.append(
                    CanFrame(
                        sequence=sequence,
                        timestamp_ns=sequence * 1_000_000,
                        arbitration_id=0x100 + (sequence % 3),
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
            frame_count=12,
            marker_count=0,
            duration_s=0.011,
        )
        source_hash = _sha256(session_path)

        container = ApplicationContainer()
        tabs = QTabWidget()
        navigator = container.create_project_navigator(tabs)
        output_messages: list[str] = []
        widget = navigator.open_session(
            session_path,
            project=project,
            inspector_sink=lambda _text: None,
            output_sink=output_messages.append,
        )
        assert widget.project is project
        assert widget.analysis_provider_combo.count() == 1
        assert (
            widget.analysis_provider_combo.currentData()
            == SESSION_STATISTICS_PROVIDER_ID
        )
        assert widget.run_analysis_button.isEnabled()
        assert widget.artifact_table.rowCount() == 0
        assert widget.tabs.tabText(widget.analysis_tab_index) == "Analizy (0)"

        widget.tabs.setCurrentIndex(widget.analysis_tab_index)
        widget.run_analysis_button.click()
        assert widget._analysis_task is not None
        assert not widget.run_analysis_button.isEnabled()
        assert widget.cancel_analysis_button.isEnabled()

        _wait_until(app, lambda: widget._analysis_task is None, timeout_s=10.0)
        assert widget.analysis_progress.value() == 100
        assert widget.analysis_progress.format() == "Gotowe — 100%"
        assert widget.artifact_table.rowCount() == 1
        assert widget.tabs.tabText(widget.analysis_tab_index) == "Analizy (1)"
        details = widget.artifact_details.toPlainText()
        assert "ARTEFAKT ANALIZY" in details
        assert "PODSUMOWANIE SESJI" in details
        assert "Ramki: 12" in details
        assert "Unikalne CAN ID: 3" in details
        artifact = widget._analysis_artifacts[0]
        assert project.absolute_path(artifact.relative_path).is_file()
        assert _sha256(session_path) == source_hash
        assert any("Analiza crt.analysis.session_statistics zakończona" in text for text in output_messages)

        assert navigator.close_session(session_path) is CloseTabResult.CLOSED
        _flush_deferred(app)
        del widget
        collect()

        reopened = navigator.open_session(
            session_path,
            project=project,
            inspector_sink=lambda _text: None,
            output_sink=output_messages.append,
        )
        assert reopened.project is project
        assert reopened.artifact_table.rowCount() == 1
        assert reopened.tabs.tabText(reopened.analysis_tab_index) == "Analizy (1)"
        assert "PODSUMOWANIE SESJI" in reopened.artifact_details.toPlainText()
        assert _sha256(session_path) == source_hash
        assert navigator.close_session(session_path) is CloseTabResult.CLOSED
        _flush_deferred(app)

        tabs.close()
        tabs.deleteLater()
        _flush_deferred(app)
        del reopened
        del navigator
        del tabs
        del project
        collect()
    return 0


def _wait_until(app: QApplication, predicate, *, timeout_s: float) -> None:
    deadline = monotonic() + timeout_s
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("timed out waiting for session analysis")
        app.processEvents()
        sleep(0.01)
    QThreadPool.globalInstance().waitForDone(5_000)
    app.processEvents()


def _flush_deferred(app: QApplication) -> None:
    QThreadPool.globalInstance().waitForDone(5_000)
    app.processEvents()
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
