from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QLabel

from app.filters import ProjectFilterRepository
from app.live_filters import ActiveFilterSet
from app.session_filters import FilteredSessionPage
from app.session_stream import read_session_header

from .session_filter_loader import FilteredSessionLoadTask
from .session_view import SessionViewWidget


_installed = False
_original_init = SessionViewWidget.__init__


def install_session_filter_integration() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    def integrated_init(self: SessionViewWidget, path, *args, **kwargs) -> None:
        self._stored_filter_generation = 0
        self._stored_filter_tasks: list[FilteredSessionLoadTask] = []
        self._stored_filter_database = _find_project_database(Path(path))
        self._stored_filter_set = _load_filter_set(self._stored_filter_database)
        self._stored_filter_signature = self._stored_filter_set.signature
        self._stored_filter_page: FilteredSessionPage | None = None

        _original_init(self, path, *args, **kwargs)

        self.stored_filter_label = QLabel()
        self.stored_filter_label.setObjectName("storedSessionFilterStatus")
        self.stored_filter_label.setStyleSheet(
            "QLabel { padding: 5px 9px; border: 1px solid palette(mid); font-weight: 600; }"
        )
        self.layout().insertWidget(1, self.stored_filter_label)
        _update_filter_label(self, loading=self._load_task is not None)

        self._stored_filter_timer = QTimer(self)
        self._stored_filter_timer.setInterval(500)
        self._stored_filter_timer.timeout.connect(lambda: _reload_filters_if_changed(self))
        self._stored_filter_timer.start()

    def integrated_start_load(self: SessionViewWidget) -> None:
        self._stored_filter_generation += 1
        generation = self._stored_filter_generation
        task = FilteredSessionLoadTask(
            self.path,
            max_rows=self.MAX_ROWS,
            filter_set=self._stored_filter_set,
        )
        task.signals.loaded.connect(
            lambda path, page, current=generation: _filtered_loaded(
                self,
                current,
                path,
                page,
            )
        )
        task.signals.failed.connect(
            lambda path, error, current=generation: _filtered_failed(
                self,
                current,
                path,
                error,
            )
        )
        self._load_task = task
        self._stored_filter_tasks.append(task)
        self._stored_filter_tasks = self._stored_filter_tasks[-3:]
        label = getattr(self, "stored_filter_label", None)
        if label is not None:
            _update_filter_label(self, loading=True)
        QThreadPool.globalInstance().start(task)

    SessionViewWidget.__init__ = integrated_init
    SessionViewWidget._start_load = integrated_start_load


def _load_filter_set(database_path: Path | None) -> ActiveFilterSet:
    if database_path is None:
        return ActiveFilterSet(())
    return ActiveFilterSet(ProjectFilterRepository(database_path).list_presets())


def _reload_filters_if_changed(widget: SessionViewWidget) -> None:
    candidate = _load_filter_set(widget._stored_filter_database)
    if candidate.signature == widget._stored_filter_signature:
        return
    widget._stored_filter_set = candidate
    widget._stored_filter_signature = candidate.signature
    widget._start_load()


def _filtered_loaded(
    widget: SessionViewWidget,
    generation: int,
    path: str,
    page: FilteredSessionPage,
) -> None:
    if generation != widget._stored_filter_generation:
        return

    loaded = list(page.frames)
    widget.frame_model.replace_frames(loaded)
    widget._stored_filter_page = page
    try:
        session = read_session_header(path)
        title = session.name
    except Exception:
        title = widget.path.name

    if widget._stored_filter_set.affects_visibility:
        text = (
            f"{title} — {path} | filtr: {page.visible_frames:,} z "
            f"{page.total_frames:,} ramek | pokazano ostatnie {len(loaded):,} "
            f"(od wyniku {page.loaded_from_visible_index:,})"
        ).replace(",", " ")
    else:
        text = (
            f"{title} — {path} | pokazano {len(loaded):,} z "
            f"{page.total_frames:,} ramek (od {page.loaded_from_visible_index:,})"
        ).replace(",", " ")

    widget.header.setText(text)
    widget.tabs.setTabText(
        widget.raw_tab_index,
        (
            f"Surowe ramki ({len(loaded):,}/{page.visible_frames:,}/"
            f"{page.total_frames:,})"
        ).replace(",", " "),
    )
    if loaded:
        widget.frame_table.scrollToBottom()
    widget.output_message.emit(
        f"Otwarto sesję {path}: wszystkie={page.total_frames}, "
        f"widoczne={page.visible_frames}, załadowane={len(loaded)}"
    )
    widget._load_task = None
    _update_filter_label(widget, loading=False)


def _filtered_failed(
    widget: SessionViewWidget,
    generation: int,
    path: str,
    error: str,
) -> None:
    if generation != widget._stored_filter_generation:
        return
    widget.header.setText(f"Nie udało się otworzyć sesji: {path}\n{error}")
    widget.output_message.emit(f"Błąd filtrowania sesji {path}: {error}")
    widget._load_task = None
    _update_filter_label(widget, loading=False, error=error)


def _update_filter_label(
    widget: SessionViewWidget,
    *,
    loading: bool,
    error: str = "",
) -> None:
    label = getattr(widget, "stored_filter_label", None)
    if label is None:
        return
    count = widget._stored_filter_set.active_count
    invalid = len(widget._stored_filter_set.validation_issues)
    if error:
        label.setText(f"Filtr zapisanej sesji: błąd — {error}")
        return
    if loading:
        label.setText(
            f"Filtr zapisanej sesji: przeliczanie… | aktywne presety: {count}"
        )
        return
    page = widget._stored_filter_page
    if count == 0:
        label.setText("Filtr zapisanej sesji: wyłączony | Plik źródłowy bez zmian")
        return
    counts = ""
    if page is not None:
        counts = (
            f" | Widoczne: {page.visible_frames:,} / Wszystkie: "
            f"{page.total_frames:,}"
        ).replace(",", " ")
    invalid_text = f" | błędne: {invalid}" if invalid else ""
    label.setText(
        f"Filtr zapisanej sesji aktywny: {count}{invalid_text}{counts} "
        "| Plik źródłowy bez zmian"
    )


def _find_project_database(session_path: Path) -> Path | None:
    resolved = session_path.resolve()
    for directory in (resolved.parent, *resolved.parents):
        candidate = directory / ".crt" / "project.sqlite"
        if candidate.is_file():
            return candidate
    return None
