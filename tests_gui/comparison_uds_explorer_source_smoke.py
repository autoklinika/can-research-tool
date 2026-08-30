from __future__ import annotations

import gc
import os
from tempfile import TemporaryDirectory
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.comparison_uds_latency import ComparisonUdsLatencyService
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.comparison_visualization_stage2d1 import ComparisonVisualizationDialog

REQUEST_ID = 0x18DA30F9
RESPONSE_ID = 0x18DAF930
REQUEST_KEY = "0:EXT:18DA30F9:data"
RESPONSE_KEY = "0:EXT:18DAF930:data"
EMPTY_REQUEST_KEY = "0:EXT:18DA31F9:data"
EMPTY_RESPONSE_KEY = "0:EXT:18DAF931:data"


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTComparisonUdsExplorerSourceSmoke")
    settings = QSettings()
    settings.clear()

    with TemporaryDirectory() as temporary:
        os.environ["CRT_APP_DATA_DIR"] = f"{temporary}/app-data"
        project = CrtProject.create(
            f"{temporary}/project",
            name="UDS explorer source smoke",
        )
        before = _create_session(project, "before", 10_000_000)
        after = _create_session(project, "after", 20_000_000)
        comparison = ComparisonSetStore(project).create(
            name="Before versus after",
            session_ids=(before.id, after.id),
            base_session_id=before.id,
        )
        service = ComparisonUdsLatencyService(project)
        useful = service.run_and_save(
            comparison,
            REQUEST_KEY,
            RESPONSE_KEY,
            timeout_ms=1_000.0,
        )
        empty = service.run_and_save(
            comparison,
            EMPTY_REQUEST_KEY,
            EMPTY_RESPONSE_KEY,
            timeout_ms=1_000.0,
        )
        assert empty.artifact.id != useful.artifact.id

        dialog = ComparisonVisualizationDialog(project, comparison.id)
        dialog.show()
        _drain(app)
        _wait_for_idle(app, dialog)

        assert dialog.uds_explorer._source_artifact_id == useful.artifact.id
        assert dialog.uds_explorer.transaction_table.rowCount() == 2
        assert "Pominięto 1 nowszy pusty artefakt" in (
            dialog.uds_explorer.status_label.text()
        )
        assert REQUEST_KEY in dialog.uds_explorer.status_label.text()
        assert RESPONSE_KEY in dialog.uds_explorer.status_label.text()

        dialog.close()
        dialog.deleteLater()
        _drain(app)
        assert QThreadPool.globalInstance().waitForDone(5_000)
        dialog = None
        project = None
        gc.collect()

    settings.clear()
    os.environ.pop("CRT_APP_DATA_DIR", None)
    print("Comparison UDS explorer preferred source smoke: OK")


def _wait_for_idle(
    app: QApplication,
    dialog: ComparisonVisualizationDialog,
) -> None:
    deadline = monotonic() + 40.0
    while monotonic() < deadline:
        _drain(app)
        if not dialog.uds_explorer._tasks:
            return
        QThreadPool.globalInstance().waitForDone(50)
    raise TimeoutError("UDS explorer preferred source did not become idle")


def _drain(app: QApplication) -> None:
    app.sendPostedEvents()
    app.processEvents()


def _create_session(
    project: CrtProject,
    name: str,
    response_delay_ns: int,
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    frames = [
        CanFrame(
            0,
            0,
            REQUEST_ID,
            _single_frame(b"\x22\xF1\x90"),
            channel=0,
            is_extended_id=True,
        ),
        CanFrame(
            1,
            response_delay_ns,
            RESPONSE_ID,
            _single_frame(b"\x62\xF1\x90\x12"),
            channel=0,
            is_extended_id=True,
        ),
    ]
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
        duration_s=response_delay_ns / 1_000_000_000.0,
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(f"session was not registered: {path}")
    return record


def _single_frame(payload: bytes) -> bytes:
    return bytes([len(payload)]) + payload


if __name__ == "__main__":
    main()
