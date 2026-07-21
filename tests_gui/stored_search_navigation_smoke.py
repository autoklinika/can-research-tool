from __future__ import annotations

import time
from tempfile import TemporaryDirectory

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication, QMainWindow

from app.filters import FilterMode, FilterPreset, ProjectFilterRepository
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from app.stored_session_controller import StoredSessionController
from gui.log_search_window import LogSearchWindow
from gui.persistent_search_index import PersistentSessionSearchIndex
from gui.session_view import SessionViewWidget
from gui.stored_search_navigation import StoredSearchNavigator


def _wait(app: QApplication, predicate, message: str, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(message)


def _selected_sequence(view: SessionViewWidget) -> int | None:
    current = view.frame_table.currentIndex()
    if not current.isValid():
        return None
    frame = view.frame_model.frame_at(current.row())
    return None if frame is None else frame.sequence


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTStoredSearchNavigationSmoke")
    QSettings().clear()

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Navigation smoke")

        preset = FilterPreset.create("Only 0x100")
        preset.enabled = True
        preset.mode = FilterMode.INCLUDE
        preset.root = {
            "type": "group",
            "operator": "and",
            "children": [
                {
                    "type": "condition",
                    "field": "can_id",
                    "operator": "eq",
                    "values": ["0x100"],
                }
            ],
        }
        ProjectFilterRepository(project.database_path).save_presets([preset])

        path = project.imported_sessions_dir / "navigation.crt.jsonl"
        can_ids = (0x100, 0x101, 0x100, 0x102, 0x100)
        with SessionStreamWriter(
            CaptureSession(name="navigation", source="test"),
            path,
            index_stride=2,
        ) as writer:
            for sequence, can_id in enumerate(can_ids):
                writer.append(
                    CanFrame(
                        sequence=sequence,
                        timestamp_ns=sequence * 1_000_000,
                        arbitration_id=can_id,
                        data=bytes((0xA0, sequence)),
                    )
                )

        project.register_session(path, name="navigation", source="test", status="ready")
        project.finalize_session(
            path,
            frame_count=len(can_ids),
            marker_count=0,
            duration_s=0.004,
        )
        session = project.session_by_path(path)
        assert session is not None

        controller = StoredSessionController(path, page_size=2)
        view = SessionViewWidget(
            path,
            controller=controller,
            protocol_summary_attacher=lambda *_args, **_kwargs: None,
        )
        parent = QMainWindow()
        parent.setCentralWidget(view)
        parent.show()

        _wait(
            app,
            lambda: not controller.state.loading and view.frame_model.rowCount() == 2,
            "initial bounded page did not load",
        )
        assert [view.frame_model.frame_at(row).sequence for row in range(2)] == [0, 1]

        index = PersistentSessionSearchIndex(project, session)
        index.start()
        _wait(app, lambda: index.is_ready, "persistent index did not become ready")

        search = LogSearchWindow(parent)
        search.set_target_index(view.frame_table, index)
        search.results.selectionModel().currentChanged.disconnect(
            search._result_selection_changed
        )
        search.results.activated.disconnect(search._activate_index)
        navigator = StoredSearchNavigator(view, cancel_widget=search, parent=parent)
        messages: list[str] = []
        view.output_message.connect(messages.append)

        def navigate(current, _previous) -> None:
            position = current.row()
            if current.isValid() and 0 <= position < len(search._hits):
                search.position_label.setText(f"{position + 1} / {len(search._hits)}")
                navigator.navigate_to_source_row(search._hits[position].row)
            else:
                search.position_label.clear()
                navigator.cancel()

        search.results.selectionModel().currentChanged.connect(navigate)
        search.show()
        app.processEvents()

        search.query_edit.setText("A0 04")
        search.start_search()
        _wait(
            app,
            lambda: (
                search.results.model().rowCount() == 1
                and not controller.state.loading
                and controller.state.page_start == 4
                and _selected_sequence(view) == 4
            ),
            "unfiltered hit did not navigate to the last stored page",
        )
        assert search.position_label.text() == "1 / 1"
        assert view.frame_model.rowCount() == 1
        assert view.frame_model.rowCount() <= controller.page_size
        assert view.frame_table.currentIndex().row() == 0

        current_result = search.results.currentIndex()
        search.results.activated.emit(current_result)
        app.processEvents()
        assert controller.state.page_start == 4
        assert _selected_sequence(view) == 4

        view.stored_apply_filters.setChecked(True)
        _wait(
            app,
            lambda: (
                controller.state.filters_enabled
                and not controller.state.loading
                and controller.state.page_start == 0
                and view.frame_model.rowCount() == 2
            ),
            "filtered first page did not load",
        )
        assert [view.frame_model.frame_at(row).sequence for row in range(2)] == [0, 2]

        search.query_edit.setText("A0 04")
        search.start_search()
        _wait(
            app,
            lambda: (
                search.results.model().rowCount() == 1
                and not controller.state.loading
                and controller.state.page_start == 2
                and _selected_sequence(view) == 4
            ),
            "filtered hit did not map to its visible page",
        )
        assert view.frame_model.rowCount() == 1
        assert view.frame_model.rowCount() <= controller.page_size

        page_before_hidden_hit = controller.state.page_start
        search.query_edit.setText("A0 01")
        search.start_search()
        _wait(
            app,
            lambda: any("jest ukryta przez aktywne filtry" in item for item in messages),
            "hidden filtered hit was not reported",
        )
        assert controller.state.page_start == page_before_hidden_hit
        assert _selected_sequence(view) == 4

        navigator.close()
        search.close()
        index.close()
        view.shutdown()
        parent.close()
        app.processEvents()
        QThreadPool.globalInstance().waitForDone(5_000)


if __name__ == "__main__":
    main()
