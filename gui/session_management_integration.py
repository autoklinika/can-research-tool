from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDir, QItemSelectionModel, QPoint, QProcess, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMenu, QMessageBox

from app.project import SessionRecord
from app.session_management import remove_session, session_artifact_paths

from .main_window import MainWindow
from .project_explorer import ROLE_NODE_TYPE, ROLE_NODE_VALUE


_PATCH_FLAG = "_crt_session_management_installed"


def install_session_management_integration() -> None:
    """Add safe session actions without coupling ProjectExplorer to disk writes."""

    if getattr(MainWindow, _PATCH_FLAG, False):
        return

    original_build_docks = MainWindow._build_docks

    def build_docks(self: MainWindow) -> None:
        original_build_docks(self)

        tree = self.explorer.tree
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._show_session_context_menu)
        tree.selectionModel().selectionChanged.connect(self._session_selection_changed)
        self.explorer.model.modelReset.connect(self._clear_session_selection)

    MainWindow._build_docks = build_docks
    MainWindow._session_selection_changed = _session_selection_changed
    MainWindow._clear_session_selection = _clear_session_selection
    MainWindow._selected_project_session = _selected_project_session
    MainWindow._show_session_context_menu = _show_session_context_menu
    MainWindow._build_session_context_menu = _build_session_context_menu
    MainWindow._reveal_selected_session = _reveal_selected_session
    MainWindow._remove_selected_session = _remove_selected_session
    MainWindow._close_session_tab_for_path = _close_session_tab_for_path
    setattr(MainWindow, _PATCH_FLAG, True)


def _session_selection_changed(self: MainWindow, *_args: Any) -> None:
    session = self._selected_project_session()
    if session is None or self.project is None:
        return
    self.inspector.setPlainText(_format_session_inspector(self.project, session))


def _clear_session_selection(self: MainWindow, *_args: Any) -> None:
    return


def _selected_project_session(self: MainWindow) -> SessionRecord | None:
    if self.project is None:
        return None
    selection_model = self.explorer.tree.selectionModel()
    if selection_model is None:
        return None
    rows = selection_model.selectedRows()
    if not rows:
        return None
    item = self.explorer.model.itemFromIndex(rows[0])
    if item is None or item.data(ROLE_NODE_TYPE) != "session":
        return None
    value = item.data(ROLE_NODE_VALUE)
    if not value:
        return None
    try:
        return self.project.session_by_path(Path(str(value)).resolve())
    except (OSError, ValueError):
        return None


def _show_session_context_menu(self: MainWindow, position: QPoint) -> None:
    tree = self.explorer.tree
    index = tree.indexAt(position)
    if not index.isValid():
        return
    item = self.explorer.model.itemFromIndex(index)
    if item is None or item.data(ROLE_NODE_TYPE) != "session":
        return

    selection_model = tree.selectionModel()
    if selection_model is None:
        return
    selection_model.select(
        index,
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    tree.setCurrentIndex(index)

    session = self._selected_project_session()
    if session is None:
        return
    menu = self._build_session_context_menu(session)
    menu.exec(tree.viewport().mapToGlobal(position))


def _build_session_context_menu(self: MainWindow, session: SessionRecord) -> QMenu:
    menu = QMenu(self.explorer.tree)

    reveal_action = menu.addAction("Idź do pliku")
    if self.project is None:
        reveal_action.setEnabled(False)
    else:
        path = self.project.absolute_path(session.relative_path)
        reveal_action.setEnabled(path.parent.is_dir())
    reveal_action.triggered.connect(self._reveal_selected_session)

    menu.addSeparator()
    imported = session.source.startswith("imported")
    remove_action = menu.addAction("Usuń z projektu" if imported else "Usuń log")
    remove_action.setToolTip(
        "Usuń wpis i wszystkie kopie oraz pliki pochodne zapisane w projekcie. "
        "Oryginalny plik źródłowy poza projektem pozostanie bez zmian."
        if imported
        else "Usuń wpis oraz wszystkie pliki tej sesji Live z dysku."
    )
    remove_action.triggered.connect(self._remove_selected_session)
    return menu


def _reveal_selected_session(self: MainWindow) -> None:
    session = self._selected_project_session()
    if session is None or self.project is None:
        return
    path = self.project.absolute_path(session.relative_path)
    if not path.parent.is_dir():
        QMessageBox.warning(
            self,
            "Nie można otworzyć lokalizacji",
            f"Folder sesji nie istnieje:\n{path.parent}",
        )
        return
    _reveal_path(path)


def _remove_selected_session(self: MainWindow) -> None:
    session = self._selected_project_session()
    if session is None or self.project is None:
        return

    imported = session.source.startswith("imported")
    path = self.project.absolute_path(session.relative_path)
    if session.status == "recording" and self._has_active_capture():
        QMessageBox.information(
            self,
            "Aktywna rejestracja",
            "Nie można usunąć sesji, która jest aktualnie rejestrowana.",
        )
        return

    artifacts = session_artifact_paths(self.project, session)
    existing_count = sum(candidate.exists() or candidate.is_symlink() for candidate in artifacts)
    if imported:
        title = "Usuń importowaną sesję z projektu"
        text = (
            f"Usunąć „{session.name}” z projektu?\n\n"
            f"Pliki projektu do usunięcia: {existing_count}\n"
            f"Lokalizacja sesji: {path}\n\n"
            "Usunięte zostaną kopie i pliki pochodne znajdujące się w projekcie. "
            "Oryginalny plik wybrany podczas importu, znajdujący się poza projektem, "
            "pozostanie bez zmian.\n\n"
            "Tej operacji nie można cofnąć."
        )
    else:
        title = "Usuń log Live"
        text = (
            f"Usunąć „{session.name}” z projektu oraz z dysku?\n\n"
            f"Lokalizacja: {path}\n"
            f"Pliki do usunięcia: {existing_count}\n\n"
            "Tej operacji nie można cofnąć."
        )

    answer = QMessageBox.question(
        self,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return

    self._close_session_tab_for_path(path)
    try:
        result = remove_session(
            self.project,
            session.id,
            delete_files=True,
        )
    except Exception as exc:
        QMessageBox.critical(self, "Nie można usunąć sesji", str(exc))
        return

    self.explorer.refresh()
    if imported:
        self.inspector.setPlainText(
            "IMPORTOWANA SESJA USUNIĘTA Z PROJEKTU\n\n"
            f"Usunięto plików projektu: {len(result.removed_files)}\n"
            "Oryginalny plik źródłowy poza projektem pozostawiono bez zmian."
        )
        self._append_output(
            f"Usunięto importowaną sesję z projektu: {session.name} | "
            f"pliki={len(result.removed_files)}"
        )
    else:
        self.inspector.setPlainText(
            "SESJA LIVE USUNIĘTA\n\n"
            f"Usunięto plików: {len(result.removed_files)}\n"
            f"Lokalizacja: {path.parent}"
        )
        self._append_output(
            f"Usunięto sesję Live: {session.name} | pliki={len(result.removed_files)}"
        )


def _close_session_tab_for_path(self: MainWindow, path: Path) -> None:
    key = f"session:{path.resolve()}"
    widget = self._tab_keys.get(key)
    if widget is None:
        return
    index = self.tabs.indexOf(widget)
    if index >= 0:
        self.tabs.removeTab(index)
    self._tab_keys.pop(key, None)
    widget.deleteLater()


def _format_session_inspector(project, session: SessionRecord) -> str:
    path = project.absolute_path(session.relative_path)
    imported = session.source.startswith("imported")
    created = _format_iso_datetime(session.created_at_utc)
    if path.is_file():
        saved = datetime.fromtimestamp(path.stat().st_mtime).astimezone().strftime(
            "%d.%m.%Y %H:%M:%S %Z"
        )
        size = _format_size(path.stat().st_size)
        file_state = "istnieje"
    else:
        saved = "brak pliku"
        size = "—"
        file_state = "nie istnieje"

    removal = (
        "z listy oraz wraz z kopiami i plikami pochodnymi w projekcie; "
        "oryginalny plik poza projektem pozostaje bez zmian"
        if imported
        else "z listy i wraz ze wszystkimi plikami sesji"
    )
    return "\n".join(
        (
            "SESJA CAN",
            "",
            f"Nazwa: {session.name}",
            f"Rodzaj: {'Importowana' if imported else 'Live'}",
            f"Status: {session.status}",
            f"Dodano do projektu: {created}",
            f"Data i godzina zapisu pliku: {saved}",
            f"Plik: {path}",
            f"Folder: {path.parent}",
            f"Stan pliku: {file_state}",
            f"Rozmiar: {size}",
            f"Ramki: {session.frame_count:,}".replace(",", " "),
            f"Znaczniki: {session.marker_count:,}".replace(",", " "),
            f"Czas sesji: {session.duration_s:.3f} s",
            f"Źródło: {session.source}",
            f"Usuwanie: {removal}",
        )
    )


def _format_iso_datetime(value: str) -> str:
    try:
        normalized = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%d.%m.%Y %H:%M:%S %Z")
    except (TypeError, ValueError):
        return value or "—"


def _format_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024.0 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{size} B"


def _reveal_path(path: Path) -> None:
    native = QDir.toNativeSeparators(str(path))
    if sys.platform.startswith("win"):
        QProcess.startDetached("explorer.exe", [f"/select,{native}"])
        return
    if sys.platform == "darwin":
        QProcess.startDetached("open", ["-R", str(path)])
        return
    target = path.parent if path.parent.is_dir() else path
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
