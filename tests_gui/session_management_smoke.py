from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QApplication

from app.models import CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.main_window import MainWindow
from gui.project_explorer import ROLE_NODE_TYPE, ROLE_NODE_VALUE
from gui.session_management_integration import (
    _format_session_inspector,
    install_session_management_integration,
)


def _find_session_item(item: QStandardItem, path: Path) -> QStandardItem | None:
    if (
        item.data(ROLE_NODE_TYPE) == "session"
        and str(item.data(ROLE_NODE_VALUE)) == str(path.resolve())
    ):
        return item
    for row in range(item.rowCount()):
        child = item.child(row)
        if child is None:
            continue
        found = _find_session_item(child, path)
        if found is not None:
            return found
    return None


def _select(window: MainWindow, item: QStandardItem) -> None:
    index = item.index()
    window.explorer.tree.selectionModel().select(
        index,
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    window.explorer.tree.setCurrentIndex(index)
    QApplication.processEvents()


def _menu_labels(window: MainWindow, path: Path) -> list[str]:
    session = window.project.session_by_path(path) if window.project is not None else None
    assert session is not None
    menu = window._build_session_context_menu(session)
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def _write_empty_session(path: Path, *, name: str, source: str) -> None:
    writer = SessionStreamWriter(CaptureSession(name=name, source=source), path)
    writer.open()
    writer.close({"clean_close": True, "frame_count": 0})


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("Autoklinika-tests")
    app.setApplicationName("CRT-session-management-smoke")
    install_session_management_integration()

    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Session smoke")

        live_path = project.live_sessions_dir / "live_case.crt.jsonl"
        _write_empty_session(live_path, name="Live case", source="kvaser-live-stream")
        project.register_session(
            live_path,
            name="Live case",
            source="kvaser-live-stream",
            status="ready",
        )

        imported_path = project.imported_sessions_dir / "imported_case.crt.jsonl"
        _write_empty_session(
            imported_path,
            name="Imported case",
            source="imported-crt-session",
        )
        project.register_session(
            imported_path,
            name="Imported case",
            source="imported-crt-session",
            status="ready",
        )

        window = MainWindow()
        window._set_project(project)
        assert (
            window.explorer.tree.contextMenuPolicy()
            == Qt.ContextMenuPolicy.CustomContextMenu
        )
        assert not hasattr(window, "session_reveal_button")
        assert not hasattr(window, "session_remove_button")

        root = window.explorer.model.item(0, 0)
        assert root is not None

        live_item = _find_session_item(root, live_path)
        assert live_item is not None
        _select(window, live_item)
        live_inspector = window.inspector.toPlainText()
        assert "Data i godzina zapisu pliku:" in live_inspector
        assert str(live_path.resolve()) in live_inspector
        assert _menu_labels(window, live_path) == ["Idź do pliku", "Usuń log"]

        imported_item = _find_session_item(root, imported_path)
        assert imported_item is not None
        _select(window, imported_item)
        imported_inspector = window.inspector.toPlainText()
        assert "Rodzaj: Importowana" in imported_inspector
        assert str(imported_path.resolve()) in imported_inspector

        imported_record = project.session_by_path(imported_path)
        assert imported_record is not None
        imported_details = _format_session_inspector(project, imported_record)
        assert "pliki pochodne w projekcie" in imported_details
        assert "oryginalny plik poza projektem pozostaje bez zmian" in imported_details
        assert _menu_labels(window, imported_path) == [
            "Idź do pliku",
            "Usuń z projektu",
        ]

        window.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
