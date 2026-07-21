from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .bounded_live_capture import BoundedLiveCaptureWidget as _BoundedLiveCaptureWidget
from .live_capture import LiveCaptureWidget
from .live_save_integration import LiveSaveIntegration


class ConfirmedStartLiveSaveIntegration(LiveSaveIntegration):
    """Resolve an unsaved log without starting the next capture immediately."""

    def start_capture(self) -> None:
        if self.has_unsaved_log:
            if not self.confirm_pending_log(reason="new_capture"):
                self._restore_pending_ui()
                return
            self._prepare_clean_live_workspace()
            return

        self._prepare_actual_capture_start()
        super().start_capture()

    def confirm_pending_log(self, *, reason: str) -> bool:
        if reason != "new_capture" or not self.has_unsaved_log:
            return super().confirm_pending_log(reason=reason)

        dialog = QMessageBox(self.widget)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Niezapisany log")
        dialog.setText("Zarejestrowany log nie został zapisany w projekcie.")
        dialog.setInformativeText(
            "Najpierw zdecyduj, co zrobić z bieżącym logiem. Po tej decyzji "
            "tabele Live zostaną wyczyszczone, ale nowa rejestracja nie rozpocznie "
            "się automatycznie. Naciśnij Start ponownie, gdy będziesz gotowy."
        )
        save_button = dialog.addButton(
            "Zapisz log",
            QMessageBox.ButtonRole.AcceptRole,
        )
        discard_button = dialog.addButton(
            "Nie zapisuj",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(
            "Anuluj",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(save_button)
        dialog.exec()

        clicked = dialog.clickedButton()
        if clicked is save_button:
            return self.save_pending_log()
        if clicked is discard_button:
            return self.discard_pending_log()
        if clicked is cancel_button:
            self._restore_pending_ui()
            return False
        self._restore_pending_ui()
        return False

    def _prepare_clean_live_workspace(self) -> None:
        widget = self.widget
        widget._analysis_session_path = None
        widget._current_session_path = None
        widget._finalized_session_path = None
        widget._last_sequence = None
        widget._last_message_sequence = None
        widget._error_shown = ""
        widget.frame_model.clear()
        widget.message_model.clear()
        widget.marker_history.clear()
        widget.frame_table.clearSelection()
        widget.message_table.clearSelection()
        widget._clear_marker_controls()
        widget.pause_view.setChecked(False)
        widget.auto_scroll.setChecked(True)
        widget.data_tabs.setCurrentIndex(widget.raw_tab_index)

        widget.state_label.setText("Stan: GOTOWY")
        widget.elapsed_label.setText("Czas: 0.0 s")
        widget.received_label.setText("Odebrane: 0")
        widget.visible_label.setText("Widoczne: 0")
        widget.outside_buffer_label.setText("Poza buforem: 0")
        widget.messages_label.setText("Wiadomości: analiza po STOP")
        widget.markers_label.setText("Znaczniki: 0")
        widget.ids_label.setText("CAN ID: 0")
        widget.data_tabs.setTabText(widget.raw_tab_index, "Surowe ramki (0)")
        widget.data_tabs.setTabText(
            widget.message_tab_index,
            "Wiadomości logiczne — po STOP",
        )
        widget.path_label.setText(f"Projekt: {widget.project.root}")

        load_button = getattr(widget, "load_deferred_logical_button", None)
        if load_button is not None:
            load_button.setEnabled(False)
        status_label = getattr(widget, "deferred_logical_status", None)
        if status_label is not None:
            status_label.setText(
                "Poprzedni log został rozstrzygnięty, a tabele wyczyszczone. "
                "Naciśnij Start ponownie, aby rozpocząć nową rejestrację."
            )

        widget._deferred_start_ready = True
        widget.output_message.emit(
            "Poprzedni log rozstrzygnięty. Widok Live wyczyszczony — "
            "naciśnij Start ponownie, aby rozpocząć rejestrację."
        )

    def _prepare_actual_capture_start(self) -> None:
        widget = self.widget
        widget._deferred_start_ready = False
        widget._analysis_session_path = None
        load_button = getattr(widget, "load_deferred_logical_button", None)
        if load_button is not None:
            load_button.setEnabled(False)
        status_label = getattr(widget, "deferred_logical_status", None)
        if status_label is not None:
            status_label.setText(
                "Rejestracja trwa. Analiza logiczna jest wyłączona, "
                "aby nie obciążać aplikacji."
            )
        widget.message_model.clear()


class BoundedLiveCaptureWidget(_BoundedLiveCaptureWidget):
    """Production Live view with deliberate two-step restart after an unsaved log."""

    def __init__(self, *args, **kwargs) -> None:
        self._deferred_start_ready = False
        kwargs.setdefault(
            "save_integration_factory",
            ConfirmedStartLiveSaveIntegration,
        )
        super().__init__(*args, **kwargs)

    def _start_capture(self) -> None:
        # Bypass the eager clearing performed by the previous bounded implementation.
        # The save integration now clears only after the operator has made a decision.
        LiveCaptureWidget._start_capture(self)

    def _refresh_view(self) -> None:
        if self._deferred_start_ready:
            self._set_capture_controls(False)
            return
        super()._refresh_view()
