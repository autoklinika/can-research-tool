from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtCore import QItemSelectionModel, QObject, QPoint, Qt
from PySide6.QtWidgets import QMenu, QMessageBox

from app.project import CrtProject, SessionRecord
from app.session_management import remove_session, session_artifact_paths
from infrastructure.desktop import reveal_path

from .project_explorer import ROLE_NODE_TYPE, ROLE_NODE_VALUE

if TYPE_CHECKING:
    from .main_window import MainWindow


class SessionManagementIntegration(QObject):
    """Connect project-session actions without modifying ``MainWindow`` at runtime."""

    def __init__(
        self,
        window: MainWindow,
        *,
        reveal_path_fn: Callable[[Path], bool] = reveal_path,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._reveal_path = reveal_path_fn

        tree = window.explorer.tree
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self.show_context_menu)
        tree.selectionModel().selectionChanged.connect(self.selection_changed)
        window.explorer.model.modelReset.connect(self.clear_selection)

    def selection_changed(self, *_args: Any) -> None:
        session = self.selected_project_session()
        project = self._window.project
        if session is not None and project is not None:
            self._window.inspector.setPlainText(
                _format_session_inspector(project, session)
            )

    def clear_selection(self, *_args: Any) -> None:
        return

    def selected_project_session(self) -> SessionRecord | None:
        window = self._window
        if window.project is None:
            return None
        selection_model = window.explorer.tree.selectionModel()
        if selection_model is None:
            return None
        rows = selection_model.selectedRows()
        if not rows:
            return None
        item = window.explorer.model.itemFromIndex(rows[0])
        if item is None or item.data(ROLE_NODE_TYPE) != "session":
            return None
        value = item.data(ROLE_NODE_VALUE)
        if not value:
            return None
        try:
            return window.project.session_by_path(Path(str(value)).resolve())
        except (OSError, ValueError):
            return None

    def show_context_menu(self, position: QPoint) -> None:
        window = self._window
        tree = window.explorer.tree
        index = tree.indexAt(position)
        if not index.isValid():
            return
        item = window.explorer.model.itemFromIndex(index)
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

        session = self.selected_project_session()
        if session is not None:
            self.build_context_menu(session).exec(tree.viewport().mapToGlobal(position))

    def build_context_menu(self, session: SessionRecord) -> QMenu:
        window = self._window
        menu = QMenu(window.explorer.tree)

        reveal_action = menu.addAction("Idź do pliku")
        if window.project is None:
            reveal_action.setEnabled(False)
        else:
            path = window.project.absolute_path(session.relative_path)
            reveal_action.setEnabled(path.parent.is_dir())
        reveal_action.triggered.connect(self.reveal_selected_session)

        menu.addSeparator()
        imported = session.source.startswith("imported")
        remove_action = menu.addAction("Usuń z projektu" if imported else "Usuń log")
        remove_action.setToolTip(
            "Usuń wpis i wszystkie kopie oraz pliki pochodne zapisane w projekcie. "
            "Oryginalny plik źródłowy poza projektem pozostanie bez zmian."
            if imported
            else "Usuń wpis oraz wszystkie pliki tej sesji Live z dysku."
        )
        remove_action.triggered.connect(self.remove_selected_session)
        return menu

    def reveal_selected_session(self) -> None:
        session = self.selected_project_session()
        project = self._window.project
        if session is None or project is None:
            return
        path = project.absolute_path(session.relative_path)
        if not path.parent.is_dir():
            QMessageBox.warning(
                self._window,
                "Nie można otworzyć lokalizacji",
                f"Folder sesji nie istnieje:\n{path.parent}",
            )
            return
        self._reveal_path(path)

    def remove_selected_session(self) -> None:
        window = self._window
        session = self.selected_project_session()
        project = window.project
        if session is None or project is None:
            return

        imported = session.source.startswith("imported")
        path = project.absolute_path(session.relative_path)
        if session.status == "recording" and window.navigator.has_active_capture():
            QMessageBox.information(
                window,
                "Aktywna rejestracja",
                "Nie można usunąć sesji, która jest aktualnie rejestrowana.",
            )
            return

        artifacts = session_artifact_paths(project, session)
        existing_count = sum(
            candidate.exists() or candidate.is_symlink() for candidate in artifacts
        )
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
            window,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        window.navigator.close_session(path)
        try:
            result = remove_session(project, session.id, delete_files=True)
        except Exception as exc:
            QMessageBox.critical(window, "Nie można usunąć sesji", str(exc))
            return

        window.explorer.refresh()
        if imported:
            window.inspector.setPlainText(
                "IMPORTOWANA SESJA USUNIĘTA Z PROJEKTU\n\n"
                f"Usunięto plików projektu: {len(result.removed_files)}\n"
                "Oryginalny plik źródłowy poza projektem pozostawiono bez zmian."
            )
            window._append_output(
                f"Usunięto importowaną sesję z projektu: {session.name} | "
                f"pliki={len(result.removed_files)}"
            )
        else:
            window.inspector.setPlainText(
                "SESJA LIVE USUNIĘTA\n\n"
                f"Usunięto plików: {len(result.removed_files)}\n"
                f"Lokalizacja: {path.parent}"
            )
            window._append_output(
                f"Usunięto sesję Live: {session.name} | "
                f"pliki={len(result.removed_files)}"
            )


def _format_session_inspector(project: CrtProject, session: SessionRecord) -> str:
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
