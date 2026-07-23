from __future__ import annotations

import gc
import hashlib
import os
from tempfile import TemporaryDirectory
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.extensions import PAYLOAD_DIFFERENCE_PROVIDER_ID
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_domain_store import ProjectDomainStore
from app.project_migrations import PROJECT_DOMAIN_SCHEMA_VERSION
from app.session_stream import SessionStreamWriter
from gui.comparison_analysis_dialog import ComparisonAnalysisDialog


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTPayloadDifferenceSmoke")
    settings = QSettings()
    settings.clear()

    with TemporaryDirectory() as temporary:
        os.environ["CRT_APP_DATA_DIR"] = f"{temporary}/app-data"
        project = CrtProject.create(
            f"{temporary}/project",
            name="Payload difference GUI",
        )
        before = _create_session(project, "before", _before_frames())
        after = _create_session(project, "after", _after_frames())
        source_hashes = {
            session.id: _sha256(project.absolute_path(session.relative_path))
            for session in (before, after)
        }
        comparison = ComparisonSetStore(project).create(
            name="Payload before versus after",
            session_ids=(before.id, after.id),
            base_session_id=before.id,
        )

        dialog = ComparisonAnalysisDialog(project, comparison.id)
        dialog.show()
        app.processEvents()

        assert dialog.provider_combo.count() == 3
        provider_index = dialog.provider_combo.findData(
            PAYLOAD_DIFFERENCE_PROVIDER_ID
        )
        assert provider_index >= 0
        dialog.provider_combo.setCurrentIndex(provider_index)
        assert dialog.run_button.isEnabled()
        assert dialog.artifact_combo.count() == 0
        dialog.run_button.click()
        _wait_for_analysis(app, dialog)

        assert dialog.artifact_combo.count() == 1
        assert dialog.sessions_table.rowCount() == 2
        assert dialog.sessions_table.columnCount() == 10
        assert dialog.changes_table.rowCount() >= 6
        assert dialog.changes_table.columnCount() == 9
        assert "Klucze payload" in dialog.summary_label.text()
        assert PAYLOAD_DIFFERENCE_PROVIDER_ID in dialog.artifact_info.text()
        assert "zakończone" in dialog.status_label.text().casefold()
        assert ComparisonSetStore(project).is_locked(comparison.id)

        for session in (before, after):
            assert (
                _sha256(project.absolute_path(session.relative_path))
                == source_hashes[session.id]
            )

        with project._connect() as connection:
            artifact_count = connection.execute(
                "SELECT COUNT(*) FROM artifacts"
            ).fetchone()[0]
        assert (
            ProjectDomainStore(project).schema_version
            == PROJECT_DOMAIN_SCHEMA_VERSION
        )
        assert artifact_count == 1

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
    print("Payload difference GUI smoke: OK")


def _wait_for_analysis(
    app: QApplication,
    dialog: ComparisonAnalysisDialog,
) -> None:
    deadline = monotonic() + 15.0
    while dialog._task is not None:
        QThreadPool.globalInstance().waitForDone(50)
        app.sendPostedEvents()
        app.processEvents()
        if monotonic() > deadline:
            raise TimeoutError("payload difference analysis did not finish")


def _before_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100, b"\x10\x20"),
        _frame(1, 1, 0x100, b"\x10\x21"),
        _frame(2, 2, 0x100, b"\x10\x20"),
        _frame(3, 3, 0x200, b"\xAA"),
        _frame(4, 4, 0x400, b"\x01\x02"),
        _frame(5, 5, 0x400, b"\x01\x02"),
    ]


def _after_frames() -> list[CanFrame]:
    return [
        _frame(0, 0, 0x100, b"\x11\x20"),
        _frame(1, 1, 0x100, b"\x11\x22"),
        _frame(2, 2, 0x100, b"\x11\x22"),
        _frame(3, 3, 0x300, b"\xBB"),
        _frame(4, 4, 0x400, b"\x01\x02"),
        _frame(5, 5, 0x400, b"\x01\x03"),
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
        is_extended_id=False,
    )


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
    record = project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=(
            max(frame.timestamp_ns for frame in frames)
            / 1_000_000_000.0
        ),
    )
    return project.session_by_path(path) or record


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
