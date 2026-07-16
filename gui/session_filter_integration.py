from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QWidget

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
        self._stored_available_filter_set = _load_filter_set(self._stored_filter_database)
        self._stored_available_filter_signature = self._stored_available_filter_set.signature
        # Saved sessions always open as raw, unfiltered data. Applying project filters
        # requires an explicit per-tab opt-in by the user.
        self._stored_filter_set = ActiveFilterSet(())
        self._stored_filter_page: FilteredSessionPage | None = None
        self._stored_page_start = 0

        _original_init(self, path, *args, **kwargs)
        _install_page_controls(self)
        _update_filter_label(self, loading=self._load_task is not None)
        _update_page_controls(self, loading=self._load_task is not None)

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
            start=self._stored_page_start,
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
        _update_filter_label(self, loading=True)
        _update_page_controls(self, loading=True)
        QThreadPool.globalInstance().start(task)

    SessionViewWidget.__init__ = integrated_init
    SessionViewWidget._start_load = integrated_start_load


def _install_page_controls(widget: SessionViewWidget) -> None:
    row_widget = QWidget(widget)
    row_widget.setObjectName("storedSessionNavigation")
    row = QHBoxLayout(row_widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(5)

    widget.stored_apply_filters = QCheckBox("Zastosuj filtry")
    widget.stored_apply_filters.setObjectName("storedSessionApplyFilters")
    widget.stored_apply_filters.setChecked(False)
    widget.stored_apply_filters.setToolTip(
        "Filtry projektu są stosowane tylko do tej zakładki i tylko po świadomym zaznaczeniu."
    )
    widget.stored_apply_filters.toggled.connect(
        lambda checked: _set_filter_application(widget, checked)
    )
    row.addWidget(widget.stored_apply_filters)

    widget.stored_filter_label = QLabel()
    widget.stored_filter_label.setObjectName("storedSessionFilterStatus")
    row.addWidget(widget.stored_filter_label)
    row.addStretch(1)

    widget.stored_page_label = QLabel("Ramki: ładowanie…")
    widget.stored_page_label.setObjectName("storedSessionPageStatus")
    row.addWidget(widget.stored_page_label)

    widget.stored_first_button = QPushButton("⏮")
    widget.stored_first_button.setToolTip("Pierwsza strona")
    widget.stored_first_button.setFixedWidth(34)
    widget.stored_first_button.clicked.connect(lambda: _request_page(widget, 0))
    row.addWidget(widget.stored_first_button)

    widget.stored_previous_button = QPushButton("◀")
    widget.stored_previous_button.setToolTip("Poprzednia strona")
    widget.stored_previous_button.setFixedWidth(34)
    widget.stored_previous_button.clicked.connect(lambda: _previous_page(widget))
    row.addWidget(widget.stored_previous_button)

    widget.stored_next_button = QPushButton("▶")
    widget.stored_next_button.setToolTip("Następna strona")
    widget.stored_next_button.setFixedWidth(34)
    widget.stored_next_button.clicked.connect(lambda: _next_page(widget))
    row.addWidget(widget.stored_next_button)

    widget.stored_last_button = QPushButton("⏭")
    widget.stored_last_button.setToolTip("Ostatnia strona")
    widget.stored_last_button.setFixedWidth(34)
    widget.stored_last_button.clicked.connect(lambda: _last_page(widget))
    row.addWidget(widget.stored_last_button)

    raw_page = widget.tabs.widget(widget.raw_tab_index)
    raw_layout = raw_page.layout() if raw_page is not None else None
    if raw_layout is not None:
        raw_layout.insertWidget(0, row_widget)


def _load_filter_set(database_path: Path | None) -> ActiveFilterSet:
    if database_path is None:
        return ActiveFilterSet(())
    return ActiveFilterSet(ProjectFilterRepository(database_path).list_presets())


def _set_filter_application(widget: SessionViewWidget, checked: bool) -> None:
    # Incrementing the generation invalidates every worker started for the previous
    # mode, so a slow filtered scan cannot overwrite the unfiltered page later.
    widget._stored_filter_generation += 1
    widget._stored_page_start = 0
    widget._stored_filter_set = (
        widget._stored_available_filter_set if checked else ActiveFilterSet(())
    )
    widget._start_load()


def _reload_filters_if_changed(widget: SessionViewWidget) -> None:
    candidate = _load_filter_set(widget._stored_filter_database)
    if candidate.signature == widget._stored_available_filter_signature:
        return
    widget._stored_available_filter_set = candidate
    widget._stored_available_filter_signature = candidate.signature
    if not widget.stored_apply_filters.isChecked():
        _update_filter_label(widget, loading=False)
        return
    widget._stored_filter_set = candidate
    widget._stored_page_start = 0
    widget._start_load()


def _request_page(widget: SessionViewWidget, start: int) -> None:
    requested = max(0, int(start))
    if (
        widget._stored_filter_page is not None
        and requested == widget._stored_page_start
        and widget._load_task is None
    ):
        return
    widget._stored_page_start = requested
    widget._start_load()


def _previous_page(widget: SessionViewWidget) -> None:
    _request_page(widget, max(0, widget._stored_page_start - widget.MAX_ROWS))


def _next_page(widget: SessionViewWidget) -> None:
    page = widget._stored_filter_page
    if page is None:
        return
    last_start = _last_page_start(page.visible_frames, widget.MAX_ROWS)
    _request_page(widget, min(last_start, widget._stored_page_start + widget.MAX_ROWS))


def _last_page(widget: SessionViewWidget) -> None:
    page = widget._stored_filter_page
    if page is None:
        return
    _request_page(widget, _last_page_start(page.visible_frames, widget.MAX_ROWS))


def _filtered_loaded(
    widget: SessionViewWidget,
    generation: int,
    path: str,
    page: FilteredSessionPage,
) -> None:
    if generation != widget._stored_filter_generation:
        return

    loaded = list(page.frames)
    widget._stored_filter_page = page
    widget._stored_page_start = page.loaded_from_visible_index
    widget.frame_model.replace_frames(loaded)
    try:
        session = read_session_header(path)
        title = session.name
    except Exception:
        title = widget.path.name

    start = page.loaded_from_visible_index
    end = start + len(loaded)
    if widget._stored_filter_set.affects_visibility:
        text = (
            f"{title} — {path} | wyniki {start + 1 if loaded else 0:,}–{end:,} "
            f"z {page.visible_frames:,} | cały log: {page.total_frames:,} ramek"
        ).replace(",", " ")
    else:
        text = (
            f"{title} — {path} | ramki {start + 1 if loaded else 0:,}–{end:,} "
            f"z {page.total_frames:,}"
        ).replace(",", " ")

    widget.header.setText(text)
    if widget._stored_filter_set.affects_visibility:
        tab_text = (
            f"Surowe ramki ({page.visible_frames:,}/{page.total_frames:,})"
        ).replace(",", " ")
    else:
        tab_text = f"Surowe ramki ({page.total_frames:,})".replace(",", " ")
    widget.tabs.setTabText(widget.raw_tab_index, tab_text)

    if loaded:
        widget.frame_table.scrollToTop()
    widget.output_message.emit(
        f"Otwarto stronę sesji {path}: zakres={start}-{end}, "
        f"widoczne={page.visible_frames}, wszystkie={page.total_frames}"
    )
    widget._load_task = None
    _update_filter_label(widget, loading=False)
    _update_page_controls(widget, loading=False)


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
    _update_page_controls(widget, loading=False)


def _update_filter_label(
    widget: SessionViewWidget,
    *,
    loading: bool,
    error: str = "",
) -> None:
    label = getattr(widget, "stored_filter_label", None)
    if label is None:
        return
    if error:
        label.setText(f"Filtry: błąd — {error}")
        return

    if not widget.stored_apply_filters.isChecked():
        available = widget._stored_available_filter_set.active_count
        text = "Filtry tej sesji: WYŁĄCZONE"
        if available:
            text += f" | dostępne presety: {available}"
    else:
        count = widget._stored_filter_set.active_count
        if count == 0:
            text = "Filtry tej sesji: włączone, brak aktywnych presetów"
        else:
            names = ", ".join(preset.name for preset in widget._stored_filter_set.presets[:2])
            if count > 2:
                names += f" +{count - 2}"
            text = f"Filtry tej sesji: {names}"
    if loading:
        text += " | ładowanie…"
    label.setText(text)


def _update_page_controls(widget: SessionViewWidget, *, loading: bool) -> None:
    label = getattr(widget, "stored_page_label", None)
    if label is None:
        return

    buttons = (
        widget.stored_first_button,
        widget.stored_previous_button,
        widget.stored_next_button,
        widget.stored_last_button,
    )
    if loading:
        label.setText("Ramki: ładowanie strony…")
        for button in buttons:
            button.setEnabled(False)
        return

    page = widget._stored_filter_page
    if page is None:
        label.setText("Ramki: —")
        for button in buttons:
            button.setEnabled(False)
        return

    start = page.loaded_from_visible_index
    end = start + len(page.frames)
    if widget._stored_filter_set.affects_visibility:
        text = (
            f"Wyniki {start + 1 if page.frames else 0:,}–{end:,} z "
            f"{page.visible_frames:,} | log {page.total_frames:,}"
        ).replace(",", " ")
    else:
        text = (
            f"Ramki {start + 1 if page.frames else 0:,}–{end:,} z "
            f"{page.total_frames:,}"
        ).replace(",", " ")
    label.setText(text)

    last_start = _last_page_start(page.visible_frames, widget.MAX_ROWS)
    widget.stored_first_button.setEnabled(start > 0)
    widget.stored_previous_button.setEnabled(start > 0)
    widget.stored_next_button.setEnabled(start < last_start)
    widget.stored_last_button.setEnabled(start < last_start)


def _last_page_start(total: int, page_size: int) -> int:
    if total <= 0:
        return 0
    return ((total - 1) // page_size) * page_size


def _find_project_database(session_path: Path) -> Path | None:
    resolved = session_path.resolve()
    for directory in (resolved.parent, *resolved.parents):
        candidate = directory / ".crt" / "project.sqlite"
        if candidate.is_file():
            return candidate
    return None
