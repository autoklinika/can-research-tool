from __future__ import annotations

from PySide6.QtCore import QModelIndex

from .live_filter_integration import LiveFilterIntegration


STREAM_FILTER_VIEW_CAPACITY = 5_000


class StreamingLiveFilterIntegration(LiveFilterIntegration):
    """Use a stream-only presentation while CAN capture is active.

    Changing a filter during an active capture clears only the GUI frame/message
    models. The sequence cursors owned by ``LiveCaptureWidget`` are deliberately
    preserved, so the next refresh contains traffic received after the change.
    CaptureService, its bounded live buffers and persistent session writers are not
    touched.

    When capture is not active, the regular background scan from
    ``LiveFilterIntegration`` remains available for the existing GUI buffer.
    """

    def __init__(self, widget) -> None:
        self._stream_reset_in_progress = False
        self._streaming_filter_view = False
        super().__init__(widget)

    def _set_filter_application(self, checked: bool) -> None:
        if not self.widget.is_capturing:
            self._streaming_filter_view = False
            super()._set_filter_application(checked)
            return

        if not checked:
            self._set_frame_display_model(False)
            self._set_message_display_model(False)

        applied = bool(checked and self.proxy.filter_set.active_count)
        self.proxy.set_filter_enabled(
            applied and self.proxy.filter_set.affects_raw_visibility
        )
        self.message_proxy.set_filter_enabled(
            applied and self.proxy.filter_set.affects_visibility
        )
        self._streaming_filter_view = applied
        self._reset_streaming_presentation()

        if applied:
            names = ", ".join(self.proxy.filter_set.active_names)
            self.widget.output_message.emit(
                f"Filtry Live włączone od bieżącego momentu: {names}"
            )
        else:
            if checked and not self.proxy.filter_set.active_count:
                self.checkbox.blockSignals(True)
                self.checkbox.setChecked(False)
                self.checkbox.blockSignals(False)
            self.widget.output_message.emit(
                "Filtry Live wyłączone — widok od bieżącego momentu pokazuje wszystkie ramki"
            )

        self._update_filter_control()
        self._update_live_counts()

    def _reload_and_update(self) -> None:
        if not self.widget.is_capturing:
            super()._reload_and_update()
            return

        changed = self.proxy.reload_project_filters()
        logical_changed = self.message_proxy.set_filter_set(self.proxy.filter_set)

        if self.proxy.filter_set.active_count == 0:
            was_checked = self.checkbox.isChecked()
            if was_checked:
                self.checkbox.blockSignals(True)
                self.checkbox.setChecked(False)
                self.checkbox.blockSignals(False)
            self.proxy.set_filter_enabled(False)
            self.message_proxy.set_filter_enabled(False)
            if was_checked:
                self._streaming_filter_view = False
                self._reset_streaming_presentation()
        elif (changed or logical_changed) and self.checkbox.isChecked():
            self.proxy.set_filter_enabled(
                self.proxy.filter_set.affects_raw_visibility
            )
            self.message_proxy.set_filter_enabled(
                self.proxy.filter_set.affects_visibility
            )
            self._streaming_filter_view = True
            self._reset_streaming_presentation()
            self.widget.output_message.emit(
                "Zmieniono filtry Live — nowy widok obowiązuje od bieżącego momentu"
            )

        self._update_filter_control()
        self._update_live_counts()

    def _source_frame_model_reset(self) -> None:
        if self._stream_reset_in_progress:
            return
        super()._source_frame_model_reset()

    def _source_message_model_reset(self) -> None:
        if self._stream_reset_in_progress:
            return
        super()._source_message_model_reset()

    def _reset_streaming_presentation(self) -> None:
        """Reset only presentation models and preserve capture tail cursors."""

        self._frame_generation += 1
        self._message_generation += 1
        self._pending_frames.clear()
        self._incremental_running_generation = None
        self._incremental_timer.stop()
        self._set_frame_display_model(False)
        self._set_message_display_model(False)

        self._stream_reset_in_progress = True
        try:
            self.widget.frame_model.clear()
            self.widget.message_model.clear()
        finally:
            self._stream_reset_in_progress = False

        if self.proxy.filter_enabled:
            self.proxy.beginResetModel()
            self.proxy.filter_scanning = False
            self.proxy.filter_ready = True
            self.proxy._frames.clear()
            self.proxy.endResetModel()
            self._set_frame_display_model(True)

        if self.message_proxy.filter_enabled:
            self.message_proxy.filter_scanning = False
            self.message_proxy.filter_ready = True
            self.message_proxy._clear_filter_cache(keep_state=True)
            # The source GUI model was just cleared, therefore this invalidation is
            # constant-cost. Future rows are evaluated incrementally by the proxy.
            self.message_proxy.invalidateFilter()
            self._set_message_display_model(True)

    def _incremental_scan_completed(
        self,
        generation: int,
        accepted_frames: object,
    ) -> None:
        super()._incremental_scan_completed(generation, accepted_frames)

        if (
            not self._streaming_filter_view
            or generation != self._frame_generation
            or not self.proxy.filter_enabled
            or not self.proxy.filter_ready
        ):
            return

        overflow = len(self.proxy._frames) - STREAM_FILTER_VIEW_CAPACITY
        if overflow <= 0:
            return

        trim_chunk = max(1, STREAM_FILTER_VIEW_CAPACITY // 10)
        remove_count = min(
            len(self.proxy._frames),
            max(overflow, trim_chunk),
        )
        self.proxy.beginRemoveRows(QModelIndex(), 0, remove_count - 1)
        del self.proxy._frames[:remove_count]
        self.proxy.endRemoveRows()
        self._update_live_counts()

    def _update_filter_control(self) -> None:
        super()._update_filter_control()
        if (
            self.widget.is_capturing
            and self.checkbox.isChecked()
            and self.proxy.filter_set.active_count
        ):
            names = ", ".join(self.proxy.filter_set.active_names)
            self.checkbox.setToolTip(
                f"Filtry Live: WŁĄCZONE. Aktywne presety: {names}. "
                "Widok działa strumieniowo od momentu aktywacji; pełny zapis sesji trwa nadal."
            )
