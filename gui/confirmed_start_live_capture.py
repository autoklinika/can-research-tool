from __future__ import annotations

import re
from datetime import datetime

from PySide6.QtWidgets import QDialog, QInputDialog, QLabel, QMessageBox

from app.capture_service import CapturePaths

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

    def save_pending_log(self, name: str | None = None) -> bool:
        if not self.has_unsaved_log:
            return False

        requested_name = name.strip() if name is not None else self._request_log_name()
        if not requested_name:
            self._restore_pending_ui()
            return False

        self._pending_name = requested_name
        return super().save_pending_log()

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

    def _request_log_name(self) -> str | None:
        suggested = datetime.now().strftime("capture_%Y%m%d_%H%M%S")
        while True:
            dialog = QInputDialog(self.widget)
            dialog.setWindowTitle("Zapisz log")
            dialog.setLabelText("Nazwa logu:")
            dialog.setInputMode(QInputDialog.InputMode.TextInput)
            dialog.setTextValue(suggested)

            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None

            name = dialog.textValue().strip()
            if name:
                return name

            QMessageBox.warning(
                self.widget,
                "Brak nazwy logu",
                "Podaj nazwę logu albo anuluj zapis.",
            )

    def _destination_paths(self, source: CapturePaths) -> CapturePaths:
        directory = self.widget.project.live_sessions_dir
        directory.mkdir(parents=True, exist_ok=True)
        original = _safe_log_filename(self._pending_name)
        base = original
        suffix = 2
        while self._destination_base_exists(directory, base):
            base = f"{original}_{suffix:02d}"
            suffix += 1
        return CapturePaths(
            session=directory / f"{base}.crt.jsonl",
            raw_frames_csv=directory / f"{base}.frames.csv",
            logical_messages_csv=directory / f"{base}.messages.csv",
            markers=directory / f"{base}.markers.jsonl",
        )

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
        widget.session_name.setText(
            datetime.now().strftime("live_temp_%Y%m%d_%H%M%S_%f")
        )
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
        self._remove_session_name_controls()

    def _remove_session_name_controls(self) -> None:
        name_field = self.session_name
        row_layout = _find_containing_layout(self.layout(), name_field)

        for label in self.findChildren(QLabel):
            if label.text().strip() != "Nazwa sesji:":
                continue
            label.hide()
            if row_layout is not None:
                row_layout.removeWidget(label)
            label.deleteLater()
            break

        name_field.hide()
        name_field.setEnabled(False)
        if row_layout is not None:
            row_layout.removeWidget(name_field)
            if not bool(self.property("crtLiveNameSpacerAdded")):
                row_layout.insertStretch(0, 1)
                self.setProperty("crtLiveNameSpacerAdded", True)

    def _start_capture(self) -> None:
        # Bypass the eager clearing performed by the previous bounded implementation.
        # The save integration now clears only after the operator has made a decision.
        LiveCaptureWidget._start_capture(self)

    def _refresh_view(self) -> None:
        if self._deferred_start_ready:
            self._set_capture_controls(False)
            return
        super()._refresh_view()


def _find_containing_layout(layout, target):
    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is target:
            return layout
        nested = item.layout()
        found = _find_containing_layout(nested, target)
        if found is not None:
            return found
    return None


def _safe_log_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return sanitized or "capture"
