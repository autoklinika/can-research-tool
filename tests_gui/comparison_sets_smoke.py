from __future__ import annotations

import gc
import hashlib
import os
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QThreadPool, QTimer, Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QApplication

from app.domain import AnalysisInput
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_domain_store import ProjectDomainStore
from app.project_migrations import PROJECT_DOMAIN_SCHEMA_VERSION
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer
from gui.comparison_sets_view import ComparisonSetDialog, ComparisonSetsView
from gui.project_explorer import ROLE_NODE_TYPE


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTComparisonSetsSmoke")
    settings = QSettings()
    settings.clear()

    with TemporaryDirectory() as temporary:
        os.environ["CRT_APP_DATA_DIR"] = f"{temporary}/app-data"
        project = CrtProject.create(
            f"{temporary}/project",
            name="Comparison GUI",
        )
        first = _create_session(project, "before-repair", frame_count=3)
        second = _create_session(project, "after-repair", frame_count=4)
        third = _create_session(project, "reference", frame_count=2)
        source_hashes = {
            session.id: _sha256(project.absolute_path(session.relative_path))
            for session in (first, second, third)
        }

        window = ApplicationContainer().create_main_window()
        window._set_project(project)
        app.processEvents()

        assert window.compare_action.isEnabled()
        window.compare_action.trigger()
        app.processEvents()
        view = window.navigator.widget("comparison-sets")
        assert isinstance(view, ComparisonSetsView)
        assert view.table.rowCount() == 0
        assert view.new_button.isEnabled()

        QTimer.singleShot(0, _complete_new_dialog)
        view.new_button.click()
        app.processEvents()

        comparison_sets = view.store.list()
        assert len(comparison_sets) == 1
        created = comparison_sets[0]
        assert created.name == "Before versus after"
        assert len(created.session_ids) == 2
        assert created.base_session_id in created.session_ids
        assert view.table.rowCount() == 1
        assert view.selected_comparison_set_id() == created.id

        explorer_item = _find_node(window.explorer.model.invisibleRootItem(), "comparison_set")
        assert explorer_item is not None
        assert explorer_item.data(Qt.ItemDataRole.UserRole + 2) == created.id

        window.navigator.close_widget(view)
        window.explorer._activate_index(explorer_item.index())
        app.processEvents()
        view = window.navigator.widget("comparison-sets")
        assert isinstance(view, ComparisonSetsView)
        assert view.selected_comparison_set_id() == created.id

        QTimer.singleShot(0, _complete_edit_dialog)
        view.edit_button.click()
        app.processEvents()
        updated = view.store.get(created.id)
        assert updated.name == "Repair validation"
        assert len(updated.session_ids) == 3

        domain_store = ProjectDomainStore(project)
        domain_store.create_analysis_run(
            provider_id="crt.test.comparison",
            provider_version="1.0.0",
            algorithm_version="1",
            inputs=(AnalysisInput(kind="comparison_set", source_id=updated.id),),
        )
        view.refresh(updated.id)
        app.processEvents()
        assert not view.edit_button.isEnabled()
        assert not view.delete_button.isEnabled()
        assert "zablokowany" in view.details_label.text().casefold()
        assert domain_store.schema_version == PROJECT_DOMAIN_SCHEMA_VERSION

        for session in (first, second, third):
            assert _sha256(project.absolute_path(session.relative_path)) == source_hashes[session.id]

        window._close_project_tabs()
        window.close()
        window.deleteLater()
        assert QThreadPool.globalInstance().waitForDone(5_000)
        app.sendPostedEvents()
        app.processEvents()

        view = None
        window = None
        domain_store = None
        project = None
        gc.collect()

    settings.clear()
    os.environ.pop("CRT_APP_DATA_DIR", None)
    print("Comparison sets GUI smoke: OK")


def _complete_new_dialog() -> None:
    dialog = QApplication.activeModalWidget()
    assert isinstance(dialog, ComparisonSetDialog)
    dialog.name_edit.setText("Before versus after")
    dialog.sessions_tree.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)
    dialog.sessions_tree.topLevelItem(1).setCheckState(0, Qt.CheckState.Checked)
    dialog._session_selection_changed()
    dialog.base_combo.setCurrentIndex(1)
    dialog._accept_if_valid()


def _complete_edit_dialog() -> None:
    dialog = QApplication.activeModalWidget()
    assert isinstance(dialog, ComparisonSetDialog)
    dialog.name_edit.setText("Repair validation")
    for index in range(dialog.sessions_tree.topLevelItemCount()):
        dialog.sessions_tree.topLevelItem(index).setCheckState(
            0,
            Qt.CheckState.Checked,
        )
    dialog._session_selection_changed()
    dialog.base_combo.setCurrentIndex(1)
    dialog._accept_if_valid()


def _find_node(root: QStandardItem, node_type: str) -> QStandardItem | None:
    for row in range(root.rowCount()):
        item = root.child(row)
        if item.data(ROLE_NODE_TYPE) == node_type:
            return item
        nested = _find_node(item, node_type)
        if nested is not None:
            return nested
    return None


def _create_session(project: CrtProject, name: str, *, frame_count: int):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(name=name, source="test", bitrate=250_000, channel=0)
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for sequence in range(frame_count):
        writer.append(
            CanFrame(
                sequence=sequence,
                timestamp_ns=sequence * 1_000_000,
                arbitration_id=0x18DAF900,
                data=bytes((sequence, 0xAA)),
                channel=0,
                is_extended_id=True,
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
        frame_count=frame_count,
        marker_count=0,
        duration_s=max(0.0, float(frame_count - 1) / 1000.0),
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
