from __future__ import annotations

from PySide6.QtWidgets import QLabel

from app.combined_filters import CombinedActiveFilterSet
from app.filter_preferences import ProjectFilterPreferences
from app.filters import ProjectFilterRepository

from .live_filter_integration import _find_layout_containing
from .streaming_live_filter_integration import StreamingLiveFilterIntegration


class FinalStreamingLiveFilterIntegration(StreamingLiveFilterIntegration):
    """Streaming Live filters with project combination mode and visible state."""

    def __init__(self, widget) -> None:
        self._preferences = ProjectFilterPreferences(widget.project.database_path)
        self._active_filter_label: QLabel | None = None
        super().__init__(widget)

        label = QLabel()
        label.setObjectName("activeLiveFilterNames")
        label.setTextInteractionFlags(label.textInteractionFlags())
        controls = _find_layout_containing(widget.layout(), self.checkbox)
        if controls is not None:
            index = controls.indexOf(self.checkbox)
            controls.insertWidget(index + 1, label)
        else:
            widget.layout().insertWidget(1, label)
        widget.active_live_filter_label = label
        self._active_filter_label = label
        self._update_filter_control()

    def _reload_combined_filter_set(self) -> bool:
        repository = ProjectFilterRepository(self.widget.project.database_path)
        candidate = CombinedActiveFilterSet(
            repository.list_presets(),
            scope="live",
            combination_mode=self._preferences.combination_mode(),
        )
        if candidate.signature == self.proxy._signature:
            return False
        self.proxy.filter_set = candidate
        self.proxy._signature = candidate.signature
        return True

    def _reload_and_update(self) -> None:
        changed = self._reload_combined_filter_set()
        logical_changed = self.message_proxy.set_filter_set(self.proxy.filter_set)

        if not self.widget.is_capturing:
            self._reload_stopped_view(changed, logical_changed)
        else:
            self._reload_streaming_view(changed, logical_changed)

        self._update_filter_control()
        self._update_live_counts()

    def _reload_stopped_view(self, changed: bool, logical_changed: bool) -> None:
        if self.proxy.filter_set.active_count == 0:
            if self.checkbox.isChecked():
                self.checkbox.blockSignals(True)
                self.checkbox.setChecked(False)
                self.checkbox.blockSignals(False)
            self._frame_generation += 1
            self._message_generation += 1
            self._set_frame_display_model(False)
            self._set_message_display_model(False)
            self.proxy.set_filter_enabled(False)
            self.message_proxy.set_filter_enabled(False)
            self._pending_frames.clear()
            self._incremental_running_generation = None
            self._incremental_timer.stop()
            return

        if not (changed or logical_changed) or not self.checkbox.isChecked():
            return
        self._set_frame_display_model(False)
        self._set_message_display_model(False)
        self.proxy.set_filter_enabled(self.proxy.filter_set.affects_raw_visibility)
        self.message_proxy.set_filter_enabled(self.proxy.filter_set.affects_visibility)
        if self.proxy.filter_enabled:
            self._schedule_frame_scan()
        else:
            self._pending_frames.clear()
            self._incremental_running_generation = None
            self._incremental_timer.stop()
        if self.message_proxy.filter_enabled:
            self._schedule_message_scan()

    def _reload_streaming_view(self, changed: bool, logical_changed: bool) -> None:
        if self.proxy.filter_set.active_count == 0:
            was_filtering = bool(
                self.proxy.filter_enabled
                or self.message_proxy.filter_enabled
                or self._streaming_filter_view
            )
            self.proxy.set_filter_enabled(False)
            self.message_proxy.set_filter_enabled(False)
            if self.checkbox.isChecked() and (
                changed or logical_changed or was_filtering
            ):
                self._streaming_filter_view = False
                self._reset_streaming_presentation()
                self.widget.output_message.emit(
                    "Brak aktywnych presetów Live — pokazuję pełny strumień; "
                    "filtrowanie wznowi się automatycznie po aktywacji presetu"
                )
            return

        if not (changed or logical_changed) or not self.checkbox.isChecked():
            return
        self.proxy.set_filter_enabled(self.proxy.filter_set.affects_raw_visibility)
        self.message_proxy.set_filter_enabled(self.proxy.filter_set.affects_visibility)
        self._streaming_filter_view = True
        self._reset_streaming_presentation()
        self.widget.output_message.emit(
            "Zmieniono filtry Live — nowy widok obowiązuje od bieżącego momentu"
        )

    def _update_filter_control(self) -> None:
        super()._update_filter_control()
        label = self._active_filter_label
        if label is None:
            return

        filter_set = self.proxy.filter_set
        mode = getattr(filter_set, "combination_mode", self._preferences.combination_mode())
        names = ", ".join(filter_set.active_names)
        if self.checkbox.isChecked() and names:
            label.setText(f"Filtry: {names} | Include: {mode.value.upper()}")
        elif self.checkbox.isChecked():
            label.setText(f"Filtry: oczekiwanie na preset | Include: {mode.value.upper()}")
        elif names:
            label.setText(
                f"Aktywne presety: {names} | zastosowanie Live: WYŁĄCZONE | "
                f"Include: {mode.value.upper()}"
            )
        else:
            label.setText(f"Filtry: brak aktywnych presetów | Include: {mode.value.upper()}")
