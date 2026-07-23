from __future__ import annotations

import gc
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QSplitter, QTableWidget

from app.project import CrtProject
from gui.project_overview import ProjectOverviewWidget


def main() -> None:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(
            f"{temporary}/project",
            name="Overview test",
            default_bitrate=250_000,
            default_receive_mode="bench",
        )

        first_path = project.live_sessions_dir / "first.crt.jsonl"
        first_path.write_text("", encoding="utf-8")
        project.register_session(first_path, name="First session", source="live")
        project.finalize_session(
            first_path,
            frame_count=4_691,
            marker_count=3,
            duration_s=14.797,
        )

        second_path = project.imported_sessions_dir / "second.crt.jsonl"
        second_path.write_text("", encoding="utf-8")
        project.register_session(
            second_path,
            name="Second session",
            source="imported-csv",
        )
        project.finalize_session(
            second_path,
            frame_count=494,
            marker_count=0,
            duration_s=0.0,
        )

        widget = ProjectOverviewWidget(project)
        widget.show()
        app.processEvents()

        table = widget.findChild(QTableWidget, "recentSessionsTable")
        details_splitter = widget.findChild(
            QSplitter,
            "projectOverviewDetailsSplitter",
        )
        assert table is not None
        assert details_splitter is not None
        assert details_splitter.orientation() == Qt.Orientation.Vertical
        assert details_splitter.count() == 2

        name_value = widget.findChild(QLabel, "selectedSessionNameValue")
        source_value = widget.findChild(QLabel, "selectedSessionSourceValue")
        frames_value = widget.findChild(QLabel, "selectedSessionFramesValue")
        duration_value = widget.findChild(QLabel, "selectedSessionDurationValue")
        path_value = widget.findChild(QLabel, "selectedSessionPathValue")
        assert name_value is not None
        assert source_value is not None
        assert frames_value is not None
        assert duration_value is not None
        assert path_value is not None

        assert table.currentRow() == 0
        assert name_value.text() == "Second session"
        assert source_value.text() == "Import"
        assert frames_value.text() == "494"
        assert duration_value.text() == "0.000 s"
        assert path_value.text().endswith("second.crt.jsonl")

        table.selectRow(1)
        app.processEvents()
        assert name_value.text() == "First session"
        assert source_value.text() == "Live"
        assert frames_value.text() == "4 691"
        assert duration_value.text() == "14.797 s"
        assert path_value.text().endswith("first.crt.jsonl")

        widget.close()
        widget.deleteLater()
        app.sendPostedEvents()
        app.processEvents()
        widget = None
        project = None
        gc.collect()


if __name__ == "__main__":
    main()
