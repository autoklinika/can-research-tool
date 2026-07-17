from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThreadPool, QTimer
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QWidget

from app.stored_session_controller import (
    StoredSessionController,
    StoredSessionPageState,
)

from .logical_filter_integration import (
    LogicalFilterScanResult,
    LogicalFilterScanTask,
    LogicalMessageFilterProxy,
)
from .logical_message_model import format_logical_message_inspector

if TYPE_CHECKING:
    from .session_view import SessionViewWidget


class StoredSessionIntegration(QObject):
    """Connect stored-session controls to raw and logical presentation filters."""

    def __init__(
        self,
        widget: SessionViewWidget,
        controller: StoredSessionController,
    ) -> None:
        super().__init__(widget)
        self._widget = widget
        self._controller = controller
        self._closed = False
        self._message_generation = 0
        self._message_tasks: list[LogicalFilterScanTask] = []
        self._install_page_controls()
        self._install_message_filter()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(25)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

        self._filter_timer = QTimer(self)
        self._filter_timer.setInterval(500)
        self._filter_timer.timeout.connect(self._reload_filters_if_changed)
        self._filter_timer.start()

        self._apply_state(self._controller.start())

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._message_generation += 1
        self._poll_timer.stop()
        self._filter_timer.stop()
        self._controller.shutdown()

    def _install_page_controls(self) -> None:
        widget = self._widget
        row_widget = QWidget(widget)
        row_widget.setObjectName("storedSessionNavigation")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)

        widget.stored_apply_filters = QCheckBox("Zastosuj filtry")
        widget.stored_apply_filters.setObjectName("storedSessionApplyFilters")
        widget.stored_apply_filters.setChecked(False)
        widget.stored_apply_filters.setToolTip(
            "Filtry projektu są stosowane do surowych ramek i wiadomości logicznych "
            "tylko w tej zakładce i po świadomym zaznaczeniu."
        )
        widget.stored_apply_filters.toggled.connect(self._set_filter_application)
        row.addWidget(widget.stored_apply_filters)

        widget.stored_filter_label = QLabel()
        widget.stored_filter_label.setObjectName("storedSessionFilterStatus")
        row.addWidget(widget.stored_filter_label)
        row.addStretch(1)

        widget.stored_page_label = QLabel("Ramki: ładowanie…")
        widget.stored_page_label.setObjectName("storedSessionPageStatus")
        row.addWidget(widget.stored_page_label)

        widget.stored_first_button = self._page_button("⏮", "Pierwsza strona")
        widget.stored_first_button.clicked.connect(self._first_page)
        row.addWidget(widget.stored_first_button)

        widget.stored_previous_button = self._page_button("◀", "Poprzednia strona")
        widget.stored_previous_button.clicked.connect(self._previous_page)
        row.addWidget(widget.stored_previous_button)

        widget.stored_next_button = self._page_button("▶", "Następna strona")
        widget.stored_next_button.clicked.connect(self._next_page)
        row.addWidget(widget.stored_next_button)

        widget.stored_last_button = self._page_button("⏭", "Ostatnia strona")
        widget.stored_last_button.clicked.connect(self._last_page)
        row.addWidget(widget.stored_last_button)

        raw_page = widget.tabs.widget(widget.raw_tab_index)
        raw_layout = raw_page.layout() if raw_page is not None else None
        if raw_layout is not None:
            raw_layout.insertWidget(0, row_widget)

    def _install_message_filter(self) -> None:
        widget = self._widget
        self.message_proxy = LogicalMessageFilterProxy(widget)
        self.message_proxy.set_filter_set(self._controller.active_filter_set)
        self.message_proxy.setSourceModel(widget.message_model)
        widget.stored_message_filter_proxy = self.message_proxy
        widget.message_table.setModel(self.message_proxy)
        widget.message_table.selectionModel().selectionChanged.connect(self._message_selected)
        widget.message_model.modelReset.connect(self._message_source_reset)
        widget.message_model.rowsRemoved.connect(self._prune_message_filter_cache)

    @staticmethod
    def _page_button(text: str, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.setFixedWidth(34)
        return button

    def _message_selected(self) -> None:
        rows = self._widget.message_table.selectionModel().selectedRows()
        if not rows:
            return
        message = self.message_proxy.message_at(rows[0].row())
        if message is not None:
            self._widget.inspector_text.emit(format_logical_message_inspector(message))

    def _poll(self) -> None:
        state = self._controller.poll()
        if state is not None:
            self._apply_state(state)

    def _reload_filters_if_changed(self) -> None:
        state = self._controller.reload_filters_if_changed()
        if state is not None:
            self._apply_state(state)

    def _set_filter_application(self, checked: bool) -> None:
        self._apply_state(self._controller.set_filters_enabled(checked))

    def _first_page(self) -> None:
        self._apply_optional_state(self._controller.first_page())

    def _previous_page(self) -> None:
        self._apply_optional_state(self._controller.previous_page())

    def _next_page(self) -> None:
        self._apply_optional_state(self._controller.next_page())

    def _last_page(self) -> None:
        self._apply_optional_state(self._controller.last_page())

    def _apply_optional_state(self, state: StoredSessionPageState | None) -> None:
        if state is not None:
            self._apply_state(state)

    def _apply_state(self, state: StoredSessionPageState) -> None:
        self._widget._apply_stored_session_state(state)
        filter_changed = self.message_proxy.set_filter_set(self._controller.active_filter_set)
        previously_enabled = self.message_proxy.filter_enabled
        self.message_proxy.set_filter_enabled(state.filters_enabled)
        if self.message_proxy.filter_enabled and (filter_changed or not previously_enabled):
            self._schedule_message_scan()
        elif not self.message_proxy.filter_enabled:
            self._message_generation += 1
        self._update_filter_label(state)
        self._update_page_controls(state)
        self._update_message_counts()

    def _message_source_reset(self) -> None:
        if self.message_proxy.filter_enabled:
            self._schedule_message_scan()
        else:
            self._update_message_counts()

    def _schedule_message_scan(self) -> None:
        if not self.message_proxy.filter_enabled:
            return
        self._message_generation += 1
        generation = self._message_generation
        messages = self.message_proxy.snapshot_messages()
        self.message_proxy.begin_background_scan()
        if not messages:
            self.message_proxy.apply_background_result(
                LogicalFilterScanResult(frozenset(), frozenset())
            )
            self._update_message_counts()
            return
        task = LogicalFilterScanTask(
            generation,
            messages,
            self.message_proxy.filter_set,
        )
        self._message_tasks.append(task)
        self._message_tasks = self._message_tasks[-3:]
        task.signals.completed.connect(self._message_scan_completed)
        task.signals.failed.connect(self._message_scan_failed)
        QThreadPool.globalInstance().start(task)
        self._update_message_counts()

    def _message_scan_completed(self, generation: int, result: object) -> None:
        if generation != self._message_generation or not self.message_proxy.filter_enabled:
            return
        if not isinstance(result, LogicalFilterScanResult):
            self._message_scan_failed(generation, "nieprawidłowy wynik workera")
            return
        self.message_proxy.apply_background_result(result)
        self._message_tasks = self._message_tasks[-2:]
        self._update_message_counts()

    def _message_scan_failed(self, generation: int, error: str) -> None:
        if generation != self._message_generation:
            return
        self.message_proxy.set_filter_enabled(False)
        self._widget.output_message.emit(f"Błąd filtrowania wiadomości zapisanej sesji: {error}")
        self._update_message_counts()

    def _prune_message_filter_cache(self, *_args: object) -> None:
        self.message_proxy.prune_to_messages(self.message_proxy.snapshot_messages())

    def _update_filter_label(self, state: StoredSessionPageState) -> None:
        if state.error:
            self._widget.stored_filter_label.setText(f"Filtry: błąd — {state.error}")
            return

        if not state.filters_enabled:
            text = "Filtry tej sesji: WYŁĄCZONE"
            if state.available_filter_count:
                text += f" | dostępne presety: {state.available_filter_count}"
        elif state.active_filter_count == 0:
            text = "Filtry tej sesji: włączone, brak aktywnych presetów"
        else:
            names = ", ".join(state.active_filter_names[:2])
            if state.active_filter_count > 2:
                names += f" +{state.active_filter_count - 2}"
            text = f"Filtry tej sesji (ramki + wiadomości): {names}"
        if state.loading:
            text += " | ładowanie…"
        if self.message_proxy.filter_scanning:
            text += " | wiadomości: przeliczanie…"
        self._widget.stored_filter_label.setText(text)

    def _update_page_controls(self, state: StoredSessionPageState) -> None:
        widget = self._widget
        buttons = (
            widget.stored_first_button,
            widget.stored_previous_button,
            widget.stored_next_button,
            widget.stored_last_button,
        )
        if state.loading:
            widget.stored_page_label.setText("Ramki: ładowanie strony…")
            for button in buttons:
                button.setEnabled(False)
            return

        page = state.page
        if page is None:
            widget.stored_page_label.setText("Ramki: —")
            for button in buttons:
                button.setEnabled(False)
            return

        start = page.loaded_from_visible_index
        end = start + len(page.frames)
        if state.filter_affects_visibility:
            text = (
                f"Wyniki {start + 1 if page.frames else 0:,}–{end:,} z "
                f"{page.visible_frames:,} | log {page.total_frames:,}"
            ).replace(",", " ")
        else:
            text = (
                f"Ramki {start + 1 if page.frames else 0:,}–{end:,} z {page.total_frames:,}"
            ).replace(",", " ")
        widget.stored_page_label.setText(text)

        widget.stored_first_button.setEnabled(start > 0)
        widget.stored_previous_button.setEnabled(start > 0)
        widget.stored_next_button.setEnabled(start < state.last_page_start)
        widget.stored_last_button.setEnabled(start < state.last_page_start)

    def _update_message_counts(self) -> None:
        visible = self.message_proxy.rowCount()
        retained = self._widget.message_model.message_count
        suffix = " — przeliczanie…" if self.message_proxy.filter_scanning else ""
        if self.message_proxy.filter_enabled:
            text = f"Wiadomości logiczne ({visible:,}/{retained:,}){suffix}"
        else:
            text = f"Wiadomości logiczne ({retained:,})"
        self._widget.tabs.setTabText(
            self._widget.message_tab_index,
            text.replace(",", " "),
        )
