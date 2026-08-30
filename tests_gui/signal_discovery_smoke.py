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

from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer
from gui.project_navigator import CloseTabResult


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Signal Discovery GUI")
        session_path = project.live_sessions_dir / "signal-discovery.crt.jsonl"
        capture = CaptureSession(
            name="Signal Discovery GUI session",
            source="test",
            bitrate=250_000,
            channel=0,
        )
        frames = (
            _frame(0, 0x200, b"\xAA\x55"),
            _frame(1, 0x123, b"\x00\x10"),
            _frame(2, 0x201, b"\xBB"),
            _frame(3, 0x123, b"\x01\x20"),
            _frame(4, 0x123, b"\x03\x30"),
            _frame(5, 0x202, b"\xCC"),
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
            duration_s=(frames[-1].timestamp_ns - frames[0].timestamp_ns) / 1e9,
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
        discovery = widget.signal_discovery_view
        assert discovery is not None
        assert widget.tabs.tabText(widget.signal_discovery_tab_index) == "Signal Discovery"
        assert discovery.run_button.isEnabled()
        assert discovery.activity_table.columnCount() == 13

        widget.tabs.setCurrentIndex(widget.signal_discovery_tab_index)
        discovery.can_id_edit.setText("123")
        discovery.channel_spin.setValue(0)
        discovery.id_format_combo.setCurrentIndex(0)
        discovery.frame_kind_combo.setCurrentIndex(0)
        discovery.run_button.click()
        assert discovery._task is not None
        assert not discovery.run_button.isEnabled()
        assert discovery.cancel_button.isEnabled()

        _wait_until(app, lambda: discovery._task is None, timeout_s=10.0)
        assert discovery.progress.value() == 100
        assert discovery.activity_table.rowCount() == 2
        assert "ramki: 3" in discovery.summary_label.text()
        assert discovery._payload is not None
        assert discovery._payload["summary"]["first_source_row"] == 1
        assert discovery._payload["summary"]["last_source_row"] == 4
        assert len(discovery.plot._series) == 3
        assert [point["source_row"] for point in discovery.plot._series] == [1, 3, 4]
        assert _sha256(session_path) == source_hash

        # Evidence navigation must use the exact stored source_row, not a new search.
        discovery.activity_table.selectRow(0)
        discovery.open_max_button.click()
        app.processEvents()
        assert widget.tabs.currentIndex() == widget.raw_tab_index
        assert widget.frame_table.currentIndex().row() == 4

        # The plotted evidence points also carry exact source_row references.
        discovery._plot_point_selected(dict(discovery.plot._series[1]))
        assert discovery.open_plot_source_button.isEnabled()
        discovery.open_plot_source_button.click()
        app.processEvents()
        assert widget.frame_table.currentIndex().row() == 3

        assert navigator.close_session(session_path) is CloseTabResult.CLOSED
        _flush_deferred(app)
        del discovery
        del widget
        collect()

        tabs.close()
        tabs.deleteLater()
        _flush_deferred(app)
        del navigator
        del tabs
        del project
        collect()
    return 0


def _frame(sequence: int, arbitration_id: int, data: bytes) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=sequence * 1_000_000,
        arbitration_id=arbitration_id,
        data=data,
        channel=0,
        is_extended_id=False,
    )


def _wait_until(app: QApplication, predicate, *, timeout_s: float) -> None:
    deadline = monotonic() + timeout_s
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("timed out waiting for Signal Discovery")
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
