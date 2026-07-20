from __future__ import annotations

from .combined_filters import CombinedActiveFilterSet
from .filter_preferences import FilterCombinationMode, ProjectFilterPreferences
from .filters import ProjectFilterRepository
from .stored_session_controller import StoredSessionController, StoredSessionPageState


class EnhancedStoredSessionController(StoredSessionController):
    """Stored-session controller using the project Include combination preference."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self._filters_enabled:
            self._active_filter_set = CombinedActiveFilterSet(
                (),
                scope="stored_session",
                combination_mode=self._combination_mode(),
            )

    def set_filters_enabled(self, enabled: bool) -> StoredSessionPageState:
        self._filters_enabled = bool(enabled)
        self._active_filter_set = (
            self._available_filter_set
            if self._filters_enabled
            else CombinedActiveFilterSet(
                (),
                scope="stored_session",
                combination_mode=self._combination_mode(),
            )
        )
        return self._submit(0)

    def _load_filter_set(self) -> CombinedActiveFilterSet:
        if self._database_path is None:
            return CombinedActiveFilterSet((), scope="stored_session")
        repository = ProjectFilterRepository(self._database_path)
        preferences = ProjectFilterPreferences(self._database_path)
        return CombinedActiveFilterSet(
            repository.list_presets(),
            scope="stored_session",
            combination_mode=preferences.combination_mode(),
        )

    def _combination_mode(self) -> FilterCombinationMode:
        if self._database_path is None:
            return FilterCombinationMode.AND
        return ProjectFilterPreferences(self._database_path).combination_mode()
