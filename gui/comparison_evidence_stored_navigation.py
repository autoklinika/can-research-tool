from __future__ import annotations

from collections.abc import Callable

from .stored_search_navigation import StoredSearchNavigator


class ComparisonStoredSearchNavigator(StoredSearchNavigator):
    """Stored-session navigation with a completion callback for evidence handoff."""

    def __init__(self, view, *, parent=None) -> None:
        super().__init__(view, parent=parent)
        self._on_selected: Callable[[], None] | None = None
        self._on_failed: Callable[[str], None] | None = None
        self._target_source_row: int | None = None

    def navigate_to_source_row(
        self,
        source_row: int,
        *,
        on_selected: Callable[[], None] | None = None,
        on_failed: Callable[[str], None] | None = None,
    ) -> None:
        if on_selected is not None or on_failed is not None:
            self._finish_failed("Nawigacja została zastąpiona nowszym żądaniem.")
            self._on_selected = on_selected
            self._on_failed = on_failed
            self._target_source_row = int(source_row)
        super().navigate_to_source_row(source_row)

    def cancel(self) -> None:
        self._finish_failed("Nawigacja została anulowana.")
        super().cancel()

    def close(self) -> None:
        self._finish_failed("Widok sesji został zamknięty.")
        super().close()

    def _select_local_row(self, local_row: int) -> None:
        super()._select_local_row(local_row)
        table = self._view.frame_table
        current = table.currentIndex()
        if not current.isValid() or current.row() != local_row:
            self._finish_failed(
                "Nie udało się potwierdzić zaznaczenia ramki źródłowej."
            )
            return
        callback = self._on_selected
        self._clear_callbacks()
        if callback is not None:
            try:
                callback()
            except RuntimeError:
                pass

    def _report_message(self, message: str) -> None:
        super()._report_message(message)
        if (
            message.startswith("Nie udało się przejść do wyniku wyszukiwania:")
            or "jest ukryta przez aktywne filtry" in message
        ):
            self._finish_failed(message)

    def _finish_failed(self, error: str) -> None:
        callback = self._on_failed
        self._clear_callbacks()
        if callback is not None:
            try:
                callback(error)
            except RuntimeError:
                pass

    def _clear_callbacks(self) -> None:
        self._on_selected = None
        self._on_failed = None
        self._target_source_row = None


__all__ = ["ComparisonStoredSearchNavigator"]
