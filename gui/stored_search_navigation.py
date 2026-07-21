from __future__ import annotations

from threading import Event
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QTabWidget, QTableView, QWidget

from app.stored_search_navigation import (
    StoredSearchLocation,
    StoredSearchNavigationCancelled,
    locate_stored_search_row,
)

if TYPE_CHECKING:
    from .session_view import SessionViewWidget


class _LocateSignals(QObject):
    completed = Signal(int, object, object)
    failed = Signal(int, str)


class _LocateTask(QRunnable):
    def __init__(
        self,
        generation: int,
        path,
        filter_set,
        filter_signature: tuple[object, ...],
        source_row: int,
        page_size: int,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.path = path
        self.filter_set = filter_set
        self.filter_signature = filter_signature
        self.source_row = source_row
        self.page_size = page_size
        self.cancel_event = Event()
        self.signals = _LocateSignals()

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            location = locate_stored_search_row(
                self.path,
                self.filter_set,
                self.source_row,
                page_size=self.page_size,
                should_cancel=self.cancel_event.is_set,
            )
        except StoredSearchNavigationCancelled:
            return
        except Exception as exc:  # pragma: no cover - reported through the GUI
            if not self.cancel_event.is_set():
                self.signals.failed.emit(self.generation, str(exc))
            return
        if not self.cancel_event.is_set():
            self.signals.completed.emit(
                self.generation,
                location,
                self.filter_signature,
            )


class StoredSearchNavigator(QObject):
    """Navigate durable raw search hits without expanding the bounded Qt model."""

    def __init__(
        self,
        view: SessionViewWidget,
        *,
        cancel_widget: QWidget | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._view = view
        self._controller = view._stored_session_controller
        self._integration = view._stored_session_integration
        self._cancel_widget = cancel_widget
        self._generation = 0
        self._closed = False
        self._tasks: list[_LocateTask] = []
        self._pending_controller_generation: int | None = None
        self._pending_location: StoredSearchLocation | None = None

        self._page_timer = QTimer(self)
        self._page_timer.setInterval(25)
        self._page_timer.timeout.connect(self._check_pending_page)

        view.destroyed.connect(self._view_destroyed)
        if cancel_widget is not None:
            cancel_widget.installEventFilter(self)

    def navigate_to_source_row(self, source_row: int) -> None:
        if self._closed:
            return

        self._generation += 1
        generation = self._generation
        self._invalidate_current_request(restore_pending_page=True)
        self._activate_view()

        filter_set = self._controller.active_filter_set
        signature = tuple(filter_set.signature)
        if not filter_set.affects_visibility:
            try:
                location = locate_stored_search_row(
                    self._controller.path,
                    filter_set,
                    source_row,
                    page_size=self._controller.page_size,
                )
            except Exception as exc:
                self._report_error(str(exc))
                return
            self._location_ready(generation, location, signature)
            return

        task = _LocateTask(
            generation,
            self._controller.path,
            filter_set,
            signature,
            int(source_row),
            self._controller.page_size,
        )
        task.signals.completed.connect(self._location_ready)
        task.signals.failed.connect(self._location_failed)
        self._tasks.append(task)
        self._tasks = self._tasks[-4:]
        QThreadPool.globalInstance().start(task)

    def cancel(self) -> None:
        if self._closed:
            return
        self._generation += 1
        self._invalidate_current_request(restore_pending_page=True)

    def close(self) -> None:
        if self._closed:
            return
        self.cancel()
        self._closed = True
        self._page_timer.stop()
        cancel_widget = self._cancel_widget
        self._cancel_widget = None
        if cancel_widget is not None:
            try:
                cancel_widget.removeEventFilter(self)
            except RuntimeError:
                pass

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._cancel_widget and event.type() == QEvent.Type.Close:
            self.cancel()
        return super().eventFilter(watched, event)

    @Slot(int, object, object)
    def _location_ready(
        self,
        generation: int,
        location: object,
        filter_signature: object,
    ) -> None:
        if self._closed or generation != self._generation:
            return
        if not isinstance(location, StoredSearchLocation):
            self._report_error("nieprawidłowa lokalizacja wyniku wyszukiwania")
            return

        current_signature = tuple(self._controller.active_filter_set.signature)
        if tuple(filter_signature) != current_signature:
            self.navigate_to_source_row(location.source_row)
            return

        if not location.visible:
            self._report_message(
                f"Ramka źródłowa {location.source_row + 1} jest ukryta przez "
                "aktywne filtry tej sesji."
            )
            return
        if location.page_start is None or location.local_row is None:
            self._report_error("wynik nie zawiera poprawnej lokalizacji strony")
            return

        state = self._controller.state
        if (
            not state.loading
            and state.page is not None
            and state.page_start == location.page_start
        ):
            self._select_local_row(location.local_row)
            return

        try:
            loading = self._controller.request_page(location.page_start)
        except RuntimeError as exc:
            self._report_error(str(exc))
            return
        if loading is None:
            self._select_local_row(location.local_row)
            return

        self._integration._apply_state(loading)
        self._pending_controller_generation = loading.generation
        self._pending_location = location
        if not self._page_timer.isActive():
            self._page_timer.start()

    @Slot(int, str)
    def _location_failed(self, generation: int, error: str) -> None:
        if self._closed or generation != self._generation:
            return
        self._report_error(error)

    def _check_pending_page(self) -> None:
        pending_generation = self._pending_controller_generation
        location = self._pending_location
        if pending_generation is None or location is None:
            self._page_timer.stop()
            return

        state = self._controller.state
        if state.generation != pending_generation:
            self._clear_pending_page()
            return
        if state.loading:
            return
        if state.error:
            self._report_error(state.error)
            self._clear_pending_page()
            return
        if (
            state.page is None
            or location.page_start is None
            or state.page_start != location.page_start
        ):
            self._report_error("załadowana strona nie odpowiada wynikowi wyszukiwania")
            self._clear_pending_page()
            return

        local_row = location.local_row
        self._clear_pending_page()
        if local_row is not None:
            self._select_local_row(local_row)

    def _select_local_row(self, local_row: int) -> None:
        table = self._view.frame_table
        model = table.model()
        if model is None or not 0 <= local_row < model.rowCount():
            self._report_error("docelowa ramka nie znajduje się na załadowanej stronie")
            return
        target = model.index(local_row, 0)
        table.setCurrentIndex(target)
        table.selectRow(local_row)
        table.scrollTo(target, QTableView.PositionAtCenter)
        table.setFocus()

    def _activate_view(self) -> None:
        view = self._view
        view.tabs.setCurrentIndex(view.raw_tab_index)
        outer_tabs = getattr(view.window(), "tabs", None)
        if isinstance(outer_tabs, QTabWidget) and outer_tabs.indexOf(view) >= 0:
            outer_tabs.setCurrentWidget(view)

    def _invalidate_current_request(self, *, restore_pending_page: bool) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        pending_generation = self._pending_controller_generation
        self._clear_pending_page()
        if not restore_pending_page or pending_generation is None:
            return

        state = self._controller.state
        if state.generation != pending_generation or not state.loading:
            return
        try:
            replacement = self._controller.request_page(state.page_start)
        except RuntimeError:
            return
        if replacement is not None:
            self._integration._apply_state(replacement)

    def _clear_pending_page(self) -> None:
        self._pending_controller_generation = None
        self._pending_location = None
        self._page_timer.stop()

    def _report_error(self, error: str) -> None:
        self._report_message(f"Nie udało się przejść do wyniku wyszukiwania: {error}")

    def _report_message(self, message: str) -> None:
        try:
            self._view.output_message.emit(message)
        except RuntimeError:
            pass

    def _view_destroyed(self, *_args: object) -> None:
        if self._closed:
            return
        self._generation += 1
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self._clear_pending_page()
        self._closed = True
