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
        project = CrtProject.create(Path(directory) / "project", name="Full Signal Plotter GUI")
        path = project.live_sessions_dir / "full-signal-plotter-gui.crt.jsonl"
        capture = CaptureSession(
            name="Full Signal Plotter GUI",
            source="test",
            bitrate=250_000,
            channel=0,
        )
        frames = (
            _frame(0, 0x200, 0xEE),
            _frame(1, 0x123, 0x10),
            _frame(2, 0x123, 0x20),
            _frame(3, 0x201, 0xDD),
            _frame(4, 0x123, 0x30),
            _frame(5, 0x123, 0x40),
        )
        with SessionStreamWriter(capture, path) as writer:
            for frame in frames:
                writer.append(frame)
        project.register_session(path, name=capture.name, source=capture.source, status="ready")
        project.finalize_session(
            path,
            frame_count=len(frames),
            marker_count=0,
            duration_s=(frames[-1].timestamp_ns - frames[0].timestamp_ns) / 1e9,
        )
        source_hash = _sha256(path)

        widget = ApplicationContainer().create_session_view(path, project=project)
        plotter = widget.signal_plotter_view
        assert plotter is not None
        tab_names = [widget.tabs.tabText(index) for index in range(widget.tabs.count())]
        assert "Signal Plotter" in tab_names
        widget.tabs.setCurrentIndex(widget.signal_plotter_tab_index)

        plotter.can_id_edit.setText("123")
        plotter.start_bit_spin.setValue(0)
        plotter.length_spin.setValue(8)
        plotter.maximum_points_spin.setValue(100)
        assert plotter.artifact_combo.count() == 0
        assert plotter.run_button.isEnabled()

        plotter.run_button.click()
        assert plotter._task is not None
        _wait_until(app, lambda: plotter._task is None, timeout_s=15.0)

        assert plotter.progress.value() == 100
        assert plotter.artifact_combo.count() == 1
        assert len(plotter.plot.points) == 4
        assert [point["source_row"] for point in plotter.plot.points] == [1, 2, 4, 5]
        assert [point["raw"] for point in plotter.plot.points] == [0x10, 0x20, 0x30, 0x40]
        assert plotter.plot.cursor_point("A")["source_row"] == 1
        assert plotter.plot.cursor_point("B")["source_row"] == 5
        assert "Δt(B-A)" in plotter.cursor_label.text()
        assert "sampling=none" in plotter.series_label.text()
        assert plotter.open_a_button.isEnabled()
        assert plotter.open_b_button.isEnabled()

        # Exact evidence navigation must use the original source_row, not a rendered point.
        plotter.open_a_button.click()
        _drain(app)
        assert widget.tabs.currentIndex() == widget.raw_tab_index
        assert widget.frame_table.currentIndex().row() == 1
        assert _sha256(path) == source_hash

        _dispose_widget(app, widget)
        del widget
        del project
        collect()
    return 0


def _frame(sequence: int, arbitration_id: int, value: int) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=(sequence + 1) * 100_000_000,
        arbitration_id=arbitration_id,
        data=bytes((value, 0x00)),
        channel=0,
        is_extended_id=False,
    )


def _wait_until(app: QApplication, predicate, *, timeout_s: float) -> None:
    deadline = monotonic() + timeout_s
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("timed out waiting for Full Signal Plotter")
        app.processEvents()
        sleep(0.01)
    QThreadPool.globalInstance().waitForDone(5_000)
    _drain(app)


def _drain(app: QApplication, cycles: int = 10) -> None:
    for _ in range(cycles):
        app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
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
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
