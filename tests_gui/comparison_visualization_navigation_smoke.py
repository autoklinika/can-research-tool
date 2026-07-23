from __future__ import annotations

import gc
import os
from tempfile import TemporaryDirectory
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer
from gui.comparison_visualization import (
    ComparisonVisualizationDialog,
    ComparisonVisualizationWidget,
)
from gui.comparison_visualization_model import STATUS_MISSING
from gui.project_navigator import ProjectNavigator


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTComparisonVisualizationNavigationSmoke")
    QSettings().clear()

    _filter_and_evidence_widget_smoke(app)
    _advanced_dialog_smoke(app)
    _coordinator_smoke(app)

    QSettings().clear()
    print("Comparison visualization navigation smoke: OK")


def _filter_and_evidence_widget_smoke(app: QApplication) -> None:
    widget = ComparisonVisualizationWidget("Evidence smoke")
    widget.resize(1400, 850)
    widget.show()
    widget.set_payloads(_payloads())
    app.processEvents()

    assert widget.filtered_row_count == 3
    widget.search_edit.setText("0x200")
    app.processEvents()
    assert widget.filtered_row_count == 1
    assert widget.table.rowCount() == 1
    assert "wszystkich: 3" in widget.rows_label.text()

    widget.search_edit.clear()
    missing_index = widget.status_filter.findData(STATUS_MISSING)
    assert missing_index >= 0
    widget.status_filter.setCurrentIndex(missing_index)
    app.processEvents()
    assert widget.filtered_row_count == 1

    requests: list[tuple[str, str]] = []
    widget.evidence_requested.connect(
        lambda session_id, key: requests.append((session_id, key))
    )
    widget.table.selectRow(0)
    app.processEvents()
    widget.inspector.evidence_button.click()
    app.processEvents()
    assert requests == [("before", "0:STD:200:data")]

    widget.clear_filters_button.click()
    app.processEvents()
    assert widget.filtered_row_count == 3
    widget.table.horizontalHeader().sectionClicked.emit(1)
    widget.table.horizontalHeader().sectionClicked.emit(1)
    app.processEvents()
    assert widget.filtered_row_count == 3

    widget.close()
    widget.deleteLater()
    _drain_events(app)


def _advanced_dialog_smoke(app: QApplication) -> None:
    with TemporaryDirectory() as temporary:
        project = CrtProject.create(
            f"{temporary}/project",
            name="Advanced controls",
        )
        before = _create_session(project, "before", (0x100,))
        after = _create_session(project, "after", (0x200,))
        comparison = ComparisonSetStore(project).create(
            name="Before versus after",
            session_ids=(before.id, after.id),
            base_session_id=before.id,
        )
        dialog = ComparisonVisualizationDialog(project, comparison.id)
        dialog.show()
        app.processEvents()

        assert not dialog.advanced_panel.isVisible()
        dialog.advanced_button.click()
        app.processEvents()
        assert dialog.advanced_panel.isVisible()
        dialog.advanced_button.click()
        app.processEvents()
        assert not dialog.advanced_panel.isVisible()

        dialog._prepare_evidence(after.id, "0:STD:200:data")
        assert dialog.pending_evidence == (after.id, "0:STD:200:data")
        dialog.close()
        dialog.deleteLater()
        _drain_events(app)

        dialog = None
        project = None
        gc.collect()


def _coordinator_smoke(app: QApplication) -> None:
    with TemporaryDirectory() as temporary:
        os.environ["CRT_APP_DATA_DIR"] = f"{temporary}/app-data"
        project = CrtProject.create(
            f"{temporary}/project",
            name="Evidence navigation",
        )
        session = _create_session(project, "evidence", (0x100, 0x200))
        session_path = project.absolute_path(session.relative_path)

        window = ApplicationContainer().create_main_window()
        window.show()
        window._set_project(project)
        app.processEvents()
        window._open_comparison_evidence(session.id, "0:STD:200:data")

        key = ProjectNavigator.session_key(session_path)
        deadline = monotonic() + 15.0
        view = None
        while monotonic() < deadline:
            QThreadPool.globalInstance().waitForDone(50)
            app.sendPostedEvents()
            app.processEvents()
            view = window.navigator.widget(key)
            if view is not None and view.frame_table.currentIndex().row() == 1:
                break
        assert view is not None
        assert window.tabs.currentWidget() is view
        assert view.tabs.currentIndex() == view.raw_tab_index
        assert view.frame_table.currentIndex().row() == 1
        assert "0x200" in view.frame_table.model().data(
            view.frame_table.model().index(1, 2)
        )

        assert QThreadPool.globalInstance().waitForDone(5_000)
        window.navigator.close_all()
        window.close()
        window.deleteLater()
        _drain_events(app)

        view = None
        window = None
        project = None
        gc.collect()
        os.environ.pop("CRT_APP_DATA_DIR", None)


def _payloads() -> dict[str, dict]:
    sessions = [
        {"id": "before", "name": "Przed", "role": "base"},
        {"id": "after", "name": "Po", "role": "compared"},
    ]
    return {
        "crt.comparison_statistics": {
            "schema": "crt.comparison_statistics",
            "sessions": sessions,
            "message_keys": [
                _key("0:STD:100:data", "100", _metrics(10), _metrics(12), []),
                _key("0:STD:200:data", "200", _metrics(7), None, ["missing"]),
                _key("0:STD:300:data", "300", None, _metrics(5), ["new"]),
            ],
        }
    }


def _key(
    message_key: str,
    arbitration_hex: str,
    baseline: dict | None,
    current: dict | None,
    reasons: list[str],
) -> dict:
    return {
        "message_key": message_key,
        "channel": 0,
        "arbitration_id_hex": arbitration_hex,
        "is_extended_id": False,
        "frame_kind": "data",
        "baseline": baseline,
        "sessions": [
            {
                "session_id": "before",
                "session_name": "Przed",
                "role": "base",
                "statistics": baseline,
                "change": {"reasons": []},
            },
            {
                "session_id": "after",
                "session_name": "Po",
                "role": "compared",
                "statistics": current,
                "change": {
                    "reasons": reasons,
                    "frequency_delta_percent": None,
                },
            },
        ],
    }


def _metrics(count: int) -> dict:
    return {
        "frame_count": count,
        "mean_positive_frequency_hz": 10.0,
    }


def _create_session(
    project: CrtProject,
    name: str,
    arbitration_ids: tuple[int, ...],
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
    for sequence, arbitration_id in enumerate(arbitration_ids):
        writer.append(
            CanFrame(
                sequence=sequence,
                timestamp_ns=sequence * 1_000_000,
                arbitration_id=arbitration_id,
                data=bytes((sequence + 1,)),
                channel=0,
            )
        )
    writer.close({"clean_close": True})
    record = project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
    project.finalize_session(
        path,
        frame_count=len(arbitration_ids),
        marker_count=0,
        duration_s=max(0, len(arbitration_ids) - 1) / 1000.0,
    )
    return project.session_by_path(path) or record


def _drain_events(app: QApplication) -> None:
    app.sendPostedEvents()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


if __name__ == "__main__":
    main()
