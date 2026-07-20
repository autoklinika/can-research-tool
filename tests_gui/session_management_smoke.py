from __future__ import annotations

import argparse
import gc
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QApplication

from app.models import CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer
from gui.main_window import MainWindow
from gui.project_navigator import CloseTabResult, ProjectNavigator
from gui.project_explorer import ROLE_NODE_TYPE, ROLE_NODE_VALUE
from gui.session_management_integration import _format_session_inspector


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


def _menu_labels(window: MainWindow, path: Path) -> list[str]:
    session = window.project.session_by_path(path) if window.project is not None else None
    assert session is not None
    menu = window.session_management.build_context_menu(session)
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def _run_phase(phase: str) -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("Autoklinika-tests")
    app.setApplicationName(f"CRT-session-management-{phase}")
    with tempfile.TemporaryDirectory() as directory:
        project = CrtProject.create(Path(directory) / "project", name="Session smoke")

        live_path = project.live_sessions_dir / "live_case.crt.jsonl"
        with SessionStreamWriter(
            CaptureSession(name="Live case", source="kvaser-live-stream"),
            live_path,
        ):
            pass
        project.register_session(
            live_path,
            name="Live case",
            source="kvaser-live-stream",
            status="ready",
        )

        imported_path = project.imported_sessions_dir / "imported_case.crt.jsonl"
        with SessionStreamWriter(
            CaptureSession(name="Imported case", source="imported-crt-session"),
            imported_path,
        ):
            pass
        project.register_session(
            imported_path,
            name="Imported case",
            source="imported-crt-session",
            status="ready",
        )

        window = ApplicationContainer().create_main_window()
        window._set_project(project)

        if phase == "tree":
            assert (
                window.explorer.tree.contextMenuPolicy()
                == Qt.ContextMenuPolicy.CustomContextMenu
            )
            assert not hasattr(window, "session_reveal_button")
            assert not hasattr(window, "session_remove_button")
            root = window.explorer.model.item(0, 0)
            assert root is not None
            assert _find_session_item(root, live_path) is not None
            assert _find_session_item(root, imported_path) is not None
            first = window.navigator.open_session(
                live_path,
                project=project,
                inspector_sink=window.inspector.setPlainText,
                output_sink=window._append_output,
            )
            second = window.navigator.open_session(
                live_path,
                project=project,
                inspector_sink=window.inspector.setPlainText,
                output_sink=window._append_output,
            )
            assert first is second
            assert window.navigator.widget(ProjectNavigator.session_key(live_path)) is first
            assert window.navigator.close_session(live_path) is CloseTabResult.CLOSED
            assert window.navigator.widget(ProjectNavigator.session_key(live_path)) is None

        elif phase == "live":
            live_record = project.session_by_path(live_path)
            assert live_record is not None
            live_details = _format_session_inspector(project, live_record)
            assert "Data i godzina zapisu pliku:" in live_details
            assert str(live_path.resolve()) in live_details
            assert _menu_labels(window, live_path) == ["Idź do pliku", "Usuń log"]

        elif phase == "imported":
            imported_record = project.session_by_path(imported_path)
            assert imported_record is not None
            imported_details = _format_session_inspector(project, imported_record)
            assert "Rodzaj: Importowana" in imported_details
            assert str(imported_path.resolve()) in imported_details
            assert "plikami pochodnymi w projekcie" in imported_details
            assert "oryginalny plik poza projektem pozostaje bez zmian" in imported_details
            assert _menu_labels(window, imported_path) == [
                "Idź do pliku",
                "Usuń z projektu",
            ]
        else:
            raise ValueError(f"unknown phase: {phase}")

        window.close()
        window.deleteLater()
        app.processEvents()
        del window
        del project
        gc.collect()
        app.processEvents()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("tree", "live", "imported"))
    args = parser.parse_args()
    _run_phase(args.phase)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
