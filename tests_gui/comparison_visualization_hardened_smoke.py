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
from gui.comparison_visualization_hardened import ComparisonVisualizationDialog


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTHardenedComparisonVisualizationSmoke")
    settings = QSettings()
    settings.clear()

    with TemporaryDirectory() as temporary:
        os.environ["CRT_APP_DATA_DIR"] = f"{temporary}/app-data"
        project = CrtProject.create(
            f"{temporary}/project",
            name="Hardened comparison visualization",
        )
        before = _create_session(project, "before", _before_frames())
        after = _create_session(project, "after", _after_frames())
        comparison = ComparisonSetStore(project).create(
            name="Before versus after",
            session_ids=(before.id, after.id),
            base_session_id=before.id,
        )

        dialog = ComparisonVisualizationDialog(project, comparison.id)
        dialog.resize(1400, 850)
        dialog.show()
        app.processEvents()

        assert dialog.run_all_button.isEnabled()
        dialog.run_all_button.click()
        _wait_until_idle(app, dialog)

        assert dialog.artifact_combo.count() == 3
        assert len(dialog.dashboard.data.artifact_schemas) == 3
        assert dialog.dashboard.table.rowCount() > 0
        assert not dialog._dashboard_tasks
        assert dialog.run_all_button.isEnabled()

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
    print("Hardened comparison visualization smoke: OK")


def _wait_until_idle(
    app: QApplication,
    dialog: ComparisonVisualizationDialog,
) -> None:
    deadline = monotonic() + 45.0
    while (
        dialog._task is not None
        or dialog._batch_total > 0
        or bool(dialog._dashboard_tasks)
    ):
        QThreadPool.globalInstance().waitForDone(50)
        app.sendPostedEvents()
        app.processEvents()
        if monotonic() > deadline:
            raise TimeoutError("hardened comparison visualization did not become idle")


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
    project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
    duration_s = (frames[-1].timestamp_ns - frames[0].timestamp_ns) / 1e9
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=duration_s,
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(f"session was not registered: {path}")
    return record


def _before_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100, b"\x10\x20"),
        _frame(1, 20_000_000, 0x200, b"\xAA"),
        _frame(2, 50_000_000, 0x100, b"\x10\x21"),
        _frame(3, 100_000_000, 0x100, b"\x10\x20"),
    ]


def _after_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100, b"\x11\x20"),
        _frame(1, 10_000_000, 0x300, b"\xBB"),
        _frame(2, 25_000_000, 0x100, b"\x11\x22"),
        _frame(3, 50_000_000, 0x100, b"\x11\x22"),
        _frame(4, 75_000_000, 0x100, b"\x11\x20"),
    ]


def _frame(
    sequence: int,
    timestamp_ns: int,
    arbitration_id: int,
    data: bytes,
) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=arbitration_id,
        data=data,
        channel=0,
    )


if __name__ == "__main__":
    main()
