from __future__ import annotations

import os
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.comparison_sets import ComparisonSetStore
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.comparison_visualization import (
    ComparisonVisualizationDialog,
    ComparisonVisualizationWidget,
)
from gui.comparison_visualization_model import STATUS_MISSING


def main() -> None:
    app = QApplication.instance() or QApplication([])
    _filter_and_evidence_widget_smoke(app)
    _advanced_dialog_smoke(app)
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
    app.sendPostedEvents()
    app.processEvents()


def _advanced_dialog_smoke(app: QApplication) -> None:
    with TemporaryDirectory() as temporary:
        project = CrtProject.create(
            f"{temporary}/project",
            name="Advanced controls",
        )
        before = _create_session(project, "before", 0x100)
        after = _create_session(project, "after", 0x200)
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
        dialog.deleteLater()
        app.sendPostedEvents()
        app.processEvents()


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


def _create_session(project: CrtProject, name: str, arbitration_id: int):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(
        name=name,
        source="test",
        bitrate=250_000,
        channel=0,
    )
    writer = SessionStreamWriter(capture, path)
    writer.open()
    writer.append(
        CanFrame(
            sequence=0,
            timestamp_ns=0,
            arbitration_id=arbitration_id,
            data=b"\x01",
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
        frame_count=1,
        marker_count=0,
        duration_s=0.0,
    )
    return project.session_by_path(path) or record


if __name__ == "__main__":
    main()
