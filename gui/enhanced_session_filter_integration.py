from __future__ import annotations

from app.filter_preferences import FilterCombinationMode

from .session_filter_integration import StoredSessionIntegration


class EnhancedStoredSessionIntegration(StoredSessionIntegration):
    """Stored-session filter status with active names and Include combination mode."""

    def _update_filter_label(self, state) -> None:
        super()._update_filter_label(state)
        if state.error:
            return
        filter_set = (
            self._controller.active_filter_set
            if state.filters_enabled
            else self._controller.available_filter_set
        )
        mode = getattr(filter_set, "combination_mode", FilterCombinationMode.AND)
        self._widget.stored_filter_label.setText(
            f"{self._widget.stored_filter_label.text()} | Include: {mode.value.upper()}"
        )
