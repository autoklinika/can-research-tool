from __future__ import annotations

import gc
import os
from tempfile import TemporaryDirectory
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.comparison_visualization_stage2c1 import (
    ComparisonVisualizationDialog,
)


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName(
        "CRTComparisonInterFrameTimingSmoke"
    )
    settings = QSettings()
    settings.clear()

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(
            f"{temporary}/project",
            name="Timing smoke",
        )
        before = _create_session(
            project,
            "before",
            (0, 10, 20, 30, 70),
        )
        after = _create_session(
            project,
            "after",
            (0, 12, 24, 36, 48),
        )
        comparison = ComparisonSetStore(project).create(
            name="Before versus after",
            session_ids=(before.id, after.id),
            base_session_id=before.id,
        )

        dialog = ComparisonVisualizationDialog(
            project,
            comparison.id,
        )
        dialog.show()
        _drain(app)
        _wait_for_idle(app, dialog)

        timing_index = dialog.result_tabs.indexOf(dialog.timing)
        assert timing_index >= 0
        assert (
            dialog.result_tabs.tabText(timing_index)
            == "Timing i jitter"
        )
        dialog.result_tabs.setCurrentIndex(timing_index)
        dialog.timing.key_edit.setText("0:STD:100:data")
        dialog.timing.gap_factor_spin.setValue(3.0)
        dialog.timing.run_button.click()
        _wait_for_idle(app, dialog)

        result = dialog.timing._result
        assert result is not None
        assert result.message_key == "0:STD:100:data"
        assert len(result.sessions) == 2
        assert result.sessions[0].gap_count == 1
        assert result.sessions[1].gap_count == 0
        assert dialog.timing.sessions_table.rowCount() == 2
        assert dialog.timing.comparisons_table.rowCount() == 1
        assert dialog.timing.evidence_table.rowCount() == 1
        artifact_id = dialog.timing._loaded_artifact_id
        assert artifact_id

        opened: list[tuple[str, int, str]] = []
        dialog.source_row_open_requested.connect(
            lambda session_id, source_row, message_key, _dialog: opened.append(
                (session_id, source_row, message_key)
            )
        )
        dialog.timing.evidence_table.selectRow(0)
        _drain(app)
        dialog.timing.open_current_button.click()
        _drain(app)
        assert opened == [
            (before.id, 6, "0:STD:100:data")
        ]
        dialog.evidence_navigation_succeeded()

        dialog.close()
        _drain(app)
        dialog.deleteLater()
        _drain(app)

        restored = ComparisonVisualizationDialog(
            project,
            comparison.id,
        )
        restored.show()
        _drain(app)
        _wait_for_idle(app, restored)
        assert restored.timing._loaded_artifact_id == artifact_id
        assert restored.timing._result is not None
        assert (
            restored.timing._result.message_key
            == "0:STD:100:data"
        )
        assert (
            "bez ponownego skanowania"
            in restored.timing.status_label.text()
        )

        restored.close()
        restored.deleteLater()
        _drain(app)
        assert QThreadPool.globalInstance().waitForDone(5_000)
        restored = None
        dialog = None
        project = None
        gc.collect()

    settings.clear()
    print(
        "Comparison inter-frame timing Stage 2C1 smoke: OK"
    )


def _wait_for_idle(
    app: QApplication,
    dialog: ComparisonVisualizationDialog,
) -> None:
    deadline = monotonic() + 40.0
    while (
        dialog.timing._tasks
        or dialog.timeline._tasks
        or dialog.timeline._storage_tasks
    ):
        QThreadPool.globalInstance().waitForDone(50)
        _drain(app)
        if monotonic() > deadline:
            raise TimeoutError(
                "comparison timing view did not become idle"
            )


def _drain(app: QApplication) -> None:
    app.sendPostedEvents()
    app.processEvents()


def _create_session(
    project: CrtProject,
    name: str,
    timestamps_ms: tuple[int, ...],
):
    frames: list[CanFrame] = []
    sequence = 0
    for index, timestamp_ms in enumerate(timestamps_ms):
        frames.append(
            CanFrame(
                sequence,
                timestamp_ms * 1_000_000,
                0x100,
                bytes((index,)),
                channel=0,
            )
        )
        sequence += 1
        if index in {1, 3}:
            frames.append(
                CanFrame(
                    sequence,
                    timestamp_ms * 1_000_000 + 1,
                    0x200,
                    b"\xAA",
                    channel=0,
                )
            )
            sequence += 1
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    writer = SessionStreamWriter(
        CaptureSession(
            name=name,
            source="test",
            bitrate=250_000,
            channel=0,
        ),
        path,
    )
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
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=(timestamps_ms[-1] - timestamps_ms[0]) / 1_000.0,
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(
            f"session was not registered: {path}"
        )
    return record


if __name__ == "__main__":
    main()
