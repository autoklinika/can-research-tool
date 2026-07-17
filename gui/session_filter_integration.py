from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QWidget

from app.stored_session_controller import (
    StoredSessionController,
    StoredSessionPageState,
)

if TYPE_CHECKING:
    from .session_view import SessionViewWidget


class StoredSessionIntegration(QObject):
    """Connect stored-session controls to the Qt-independent controller."""

    def __init__(
        self,
        widget: SessionViewWidget,
        controller: StoredSessionController,
    ) -> None:
        super().__init__(widget)
        self._widget = widget
        self._controller = controller
        self._closed = False
        self._install_page_controls()

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
            "Filtry projektu są stosowane tylko do tej zakładki i tylko po świadomym zaznaczeniu."
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

    @staticmethod
    def _page_button(text: str, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.setFixedWidth(34)
        return button

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
        self._update_filter_label(state)
        self._update_page_controls(state)

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
            text = f"Filtry tej sesji: {names}"
        if state.loading:
            text += " | ładowanie…"
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
                f"Ramki {start + 1 if page.frames else 0:,}–{end:,} z "
                f"{page.total_frames:,}"
            ).replace(",", " ")
        widget.stored_page_label.setText(text)

        widget.stored_first_button.setEnabled(start > 0)
        widget.stored_previous_button.setEnabled(start > 0)
        widget.stored_next_button.setEnabled(start < state.last_page_start)
        widget.stored_last_button.setEnabled(start < state.last_page_start)
