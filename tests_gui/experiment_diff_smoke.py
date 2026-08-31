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

from app.comparison_sets import ComparisonSetStore
from app.marker_stream import MarkerStreamWriter, marker_path_for_session
from app.markers import CaptureMarker, MarkerPreset
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.comparison_visualization_stage2d1 import ComparisonVisualizationDialog
from gui.experiment_diff_view import ExperimentDiffView


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Experiment Diff GUI")
        target = MarkerPreset.create("EGR disconnected", "F3")
        control = MarkerPreset.create("Control", "F4")
        first = _session(project, "first", target, control, 12)
        second = _session(project, "second", target, control, 16)
        hashes = {
            first.id: _sha256(project.absolute_path(first.relative_path)),
            second.id: _sha256(project.absolute_path(second.relative_path)),
        }
        comparison = ComparisonSetStore(project).create(
            name="EGR correlation",
            session_ids=(first.id, second.id),
            base_session_id=first.id,
        )

        view = ExperimentDiffView(project, comparison)
        view.show()
        _drain(app)
        assert view.target_combo.count() == 2
        assert view.control_combo.count() == 3
        assert view.run_button.isEnabled()

        _select_preset(view.target_combo, target.id)
        _select_preset(view.control_combo, control.id)
        view.pre_spin.setValue(30.0)
        view.post_spin.setValue(50.0)
        view.run_button.click()
        assert view._task is not None
        _wait_until(app, lambda: view._task is None, timeout_s=20.0)

        assert view.progress.value() == 100
        assert view.table.rowCount() == 1
        assert view.table.item(0, 1).text() == "123"
        assert view.table.item(0, 4).text() == "0"
        assert view.table.item(0, 5).text() == "2"
        assert view.table.item(0, 6).text() == "2/2"
        assert view.table.item(0, 7).text() == "0/2"
        assert view.table.item(0, 8).text() == "0->1"
        assert view.table.item(0, 10).text() == "14.000"
        assert view.artifact_combo.count() == 1
        assert "Target:" in view.summary_label.text()

        view.table.selectRow(0)
        _drain(app)
        assert view.evidence_combo.count() == 4
        assert view.open_before_button.isEnabled()
        assert view.open_after_button.isEnabled()

        requests: list[tuple[str, int, str]] = []
        view.source_row_requested.connect(
            lambda session_id, source_row, message_key: requests.append(
                (session_id, source_row, message_key)
            )
        )

        # First evidence row is a changed target experiment.
        view.open_before_button.click()
        view.open_after_button.click()
        _drain(app)
        assert requests[0][1] == 0
        assert requests[1][1] == 1
        assert requests[0][2] == "0:STD:123:data"
        assert requests[1][2] == "0:STD:123:data"

        # Control evidence is preserved even though the candidate did not change.
        view.evidence_combo.setCurrentIndex(2)
        _drain(app)
        assert "CTRL" in view.evidence_combo.currentText()
        assert "stan 1→1" in view.evidence_label.text()
        view.open_before_button.click()
        view.open_after_button.click()
        _drain(app)
        assert len(requests) == 4
        assert requests[2][1] == 2
        assert requests[3][1] == 3
        assert requests[2][2] == "0:STD:123:data"
        assert requests[3][2] == "0:STD:123:data"

        for session_id, expected in hashes.items():
            record = next(item for item in project.list_sessions() if item.id == session_id)
            assert _sha256(project.absolute_path(record.relative_path)) == expected

        # Production comparison window must expose the dedicated workspace.
        dialog = ComparisonVisualizationDialog(project, comparison.id)
        tab_names = [dialog.result_tabs.tabText(index) for index in range(dialog.result_tabs.count())]
        assert "Experiment Diff" in tab_names
        assert dialog.experiment_diff is not None
        dialog.close_for_project_change()
        dialog.close()
        view.cancel_all()
        view.close()
        _drain(app)
        del dialog
        del view
        collect()
        del project
        collect()
    return 0


def _session(
    project: CrtProject,
    name: str,
    target: MarkerPreset,
    control: MarkerPreset,
    target_delay_ms: int,
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    frames = (
        _frame(0, 90_000_000, b"\x00"),
        _frame(1, (100 + target_delay_ms) * 1_000_000, b"\x04"),
        _frame(2, 290_000_000, b"\x04"),
        _frame(3, 320_000_000, b"\x04"),
    )
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True, "frame_count": len(frames)})
    record = project.register_session(path, name=name, source="test", status="ready")
    project.finalize_session(path, frame_count=4, marker_count=2, duration_s=0.32)

    markers = MarkerStreamWriter(marker_path_for_session(path), presets=(target, control))
    markers.open()
    markers.append(CaptureMarker.from_preset(target, 100_000_000, source="test"))
    markers.append(CaptureMarker.from_preset(control, 300_000_000, source="test"))
    markers.close()
    return project.session_by_path(path) or record


def _frame(sequence: int, timestamp_ns: int, data: bytes) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=0x123,
        data=data,
        channel=0,
        is_extended_id=False,
    )


def _select_preset(combo, preset_id: str) -> None:
    selector = f"preset:{preset_id}"
    for index in range(combo.count()):
        if str(combo.itemData(index) or "") == selector:
            combo.setCurrentIndex(index)
            return
    raise AssertionError(f"selector not found: {selector}")


def _wait_until(app: QApplication, predicate, *, timeout_s: float) -> None:
    deadline = monotonic() + timeout_s
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("timed out waiting for Experiment Diff")
        app.processEvents()
        sleep(0.01)
    QThreadPool.globalInstance().waitForDone(5_000)
    _drain(app)


def _drain(app: QApplication, cycles: int = 12) -> None:
    # Flush queued QTimer/singleShot callbacks before waiting. Some comparison
    # tabs schedule background artifact loads during construction; waiting first
    # would miss a task that starts on the next processEvents() cycle and could
    # leave project.sqlite open while TemporaryDirectory is being removed.
    for _ in range(cycles):
        app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()

    pool = QThreadPool.globalInstance()
    pool.waitForDone(5_000)

    # Deliver completion/deletion signals emitted by workers, then perform one
    # final wait in case those callbacks schedule bounded follow-up work.
    for _ in range(cycles):
        app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    pool.waitForDone(5_000)
    app.processEvents()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
