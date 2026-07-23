from __future__ import annotations

import os
import pickle
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QThreadPool
from PySide6.QtWidgets import QCheckBox, QGridLayout, QWidget

from app.logical_records import logical_message_path_for_session

from .external_logical_session_view import ExternalLogicalSessionViewWidget
from .logical_message_model import format_logical_message_inspector
from .stored_logical_message_panel import (
    StoredLogicalCriteria,
    parse_data_pattern,
    parse_time_filter,
)
from .stored_logical_sql_model import (
    StoredLogicalSqlFilterTask,
    StoredLogicalSqlModel,
)


class SqliteLogicalSessionViewWidget(ExternalLogicalSessionViewWidget):
    """Stored-session view backed by a persistent, virtual SQLite message cache."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._display_model = StoredLogicalSqlModel(self)
        self.message_table.setModel(self._display_model)
        self.message_table.setItemDelegateForColumn(4, self._protocol_delegate)
        self.message_table.selectionModel().selectionChanged.connect(
            self._display_message_selected
        )
        self._install_project_filter_toggle()

    def _install_project_filter_toggle(self) -> None:
        page = self.tabs.widget(self.message_tab_index)
        body = page.findChild(QWidget, "logicalSectionBody") if page is not None else None
        grid = body.layout() if body is not None else None
        self.apply_project_filters = QCheckBox("Zastosuj filtry projektu", body)
        self.apply_project_filters.setObjectName("applyStoredLogicalProjectFilters")
        self.apply_project_filters.setToolTip(
            "Stosuje aktywne presety projektu do wiadomości logicznych tak samo jak w Live."
        )
        self.apply_project_filters.toggled.connect(self._project_filter_toggled)
        if isinstance(grid, QGridLayout):
            grid.addWidget(self.apply_project_filters, 1, 9, 1, 3)

    def _project_filter_toggled(self, checked: bool) -> None:
        stored_checkbox = getattr(self, "stored_apply_filters", None)
        if stored_checkbox is not None and stored_checkbox.isChecked() != checked:
            stored_checkbox.setChecked(checked)
        if self._messages_ready:
            self._apply_message_filters()

    def reload_logical_messages(self, dbc_paths: tuple[Path, ...]) -> None:
        self._dbc_paths = tuple(Path(item) for item in dbc_paths)
        self._stop_logical_process()
        self._local_filter_generation += 1
        self._messages_ready = False
        self._message_loading = False
        self._display_model.close_cache()
        self.message_table.hide()
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(0)
        self.external_message_progress.setFormat("Oczekiwanie")
        self.external_message_status.setText(
            "Dekodery lub aktywne DBC zmieniły się. Obraz zostanie przebudowany."
        )
        self.tabs.setTabText(
            self.message_tab_index,
            "Wiadomości logiczne — kliknij, aby przebudować",
        )
        if self.tabs.currentIndex() == self.message_tab_index:
            self._start_embedded_load(force=True)

    def _start_embedded_load(self, checked: bool = False, *, force: bool = False) -> None:
        del checked
        if self._message_loading:
            return
        force = bool(force or self.sender() is self.external_message_button)
        message_path = logical_message_path_for_session(self.path)
        self._stop_logical_process()
        self._cleanup_result_file()

        descriptor, result_name = tempfile.mkstemp(
            prefix="crt-logical-cache-",
            suffix=".pickle",
        )
        os.close(descriptor)
        self._logical_result_path = Path(result_name)
        self._logical_result_path.unlink(missing_ok=True)
        self._logical_stdout_buffer = ""

        process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("PYTHONIOENCODING", "utf-8")
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._consume_process_stdout)
        process.finished.connect(self._logical_process_finished)
        process.errorOccurred.connect(self._logical_process_error)
        self._logical_process = process

        script_path = (
            Path(__file__).resolve().parent.parent / "crt_logical_messages_worker.py"
        )
        arguments = [
            str(script_path),
            str(self.path),
            "--output",
            str(self._logical_result_path),
        ]
        for dbc_path in self._dbc_paths:
            arguments.extend(("--dbc", str(dbc_path)))
        if force:
            arguments.append("--force")

        self._message_load_generation += 1
        self._message_loading = True
        self._messages_ready = False
        self._local_filter_generation += 1
        self._display_model.close_cache()
        self.message_table.hide()
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(0)
        self.external_message_progress.setFormat("Ładowanie — 0%")
        if force:
            self.external_message_status.setText("Wymuszona przebudowa obrazu analitycznego…")
        elif message_path.is_file():
            self.external_message_status.setText(
                f"Sprawdzanie cache dla {message_path.name}…"
            )
        else:
            self.external_message_status.setText(
                f"Sprawdzanie cache dla {self.path.name}…"
            )
        self.tabs.setTabText(
            self.message_tab_index,
            "Wiadomości logiczne — ładowanie…",
        )
        process.start(sys.executable, arguments)

    def _logical_process_finished(self, exit_code: int, exit_status) -> None:
        process = self._logical_process
        if process is None:
            return
        self._consume_process_stdout()
        if self._logical_stdout_buffer.strip():
            self._handle_process_line(self._logical_stdout_buffer.strip())
        self._logical_stdout_buffer = ""
        error_text = bytes(process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        ).strip()
        normal_exit = exit_status == QProcess.ExitStatus.NormalExit
        process.deleteLater()
        self._logical_process = None
        if not normal_exit or exit_code != 0:
            detail = error_text.splitlines()[-1] if error_text else (
                f"proces zakończył się kodem {exit_code}"
            )
            self._show_load_failure(detail)
            self._cleanup_result_file()
            return

        result_path = self._logical_result_path
        if result_path is None or not result_path.is_file():
            self._show_load_failure("proces nie utworzył opisu cache")
            self._cleanup_result_file()
            return
        try:
            with result_path.open("rb") as handle:
                result = pickle.load(handle)
            cache_path = Path(result["cache_path"])
            total_messages = int(result["total"])
            source = str(result["source"])
            path = str(result["path"])
            reused = bool(result.get("reused", False))
            self._display_model.set_cache(cache_path)
        except (OSError, KeyError, TypeError, ValueError, pickle.PickleError, Exception) as exc:
            self._show_load_failure(f"nie można otworzyć cache: {exc}")
            self._cleanup_result_file()
            return

        if self._display_model.total_messages != total_messages:
            self._show_load_failure(
                f"cache zawiera {self._display_model.total_messages} z {total_messages} wiadomości"
            )
            self._cleanup_result_file()
            return

        self._populate_filter_choices_from_cache()
        self.message_table.show()
        self._message_loading = False
        self._messages_ready = True
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(100)
        self.external_message_progress.setFormat("Gotowe — 100%")
        cache_state = "otwarto zapisany obraz" if reused else "zbudowano i zapisano obraz"
        self.external_message_status.setText(
            f"{cache_state}: {total_messages:,} wiadomości".replace(",", " ")
        )
        self.tabs.setTabText(
            self.message_tab_index,
            f"Wiadomości logiczne ({total_messages:,})".replace(",", " "),
        )
        source_text = "messages.csv" if source.startswith("messages-csv") else source
        if source.endswith("+dbc"):
            source_text += " + DBC"
        self.output_message.emit(
            f"Wiadomości logiczne {path}: {cache_state}, {total_messages} ({source_text})"
        )
        self._cleanup_result_file()

    def _populate_filter_choices_from_cache(self) -> None:
        selected_protocol = self.protocol_filter.currentData() or ""
        selected_sender = self.sender_filter.currentData() or ""
        protocols, senders = self._display_model.filter_choices()
        self.protocol_filter.blockSignals(True)
        self.protocol_filter.clear()
        self.protocol_filter.addItem("Wszystkie", "")
        for label, value in protocols:
            self.protocol_filter.addItem(label, value)
        self.protocol_filter.setCurrentIndex(
            max(0, self.protocol_filter.findData(selected_protocol))
        )
        self.protocol_filter.blockSignals(False)
        self.sender_filter.blockSignals(True)
        self.sender_filter.clear()
        self.sender_filter.addItem("Wszystkie", "")
        for sender in senders:
            self.sender_filter.addItem(sender, sender)
        self.sender_filter.setCurrentIndex(
            max(0, self.sender_filter.findData(selected_sender))
        )
        self.sender_filter.blockSignals(False)

    def _apply_message_filters(self) -> None:
        if not self._messages_ready or self._display_model.cache_path is None:
            self._start_embedded_load()
            return
        try:
            offset_text = self.data_offset_filter.text().strip()
            offset = int(offset_text, 0) if offset_text else None
            criteria = StoredLogicalCriteria(
                protocol=str(self.protocol_filter.currentData() or ""),
                sender=str(self.sender_filter.currentData() or ""),
                identity_text=self.identity_filter.text().strip(),
                time_from_ns=parse_time_filter(self.time_from_filter.text()),
                time_to_ns=parse_time_filter(self.time_to_filter.text()),
                data_offset=offset,
                data_pattern=parse_data_pattern(self.data_value_filter.text()),
                only_errors=self.only_errors_filter.isChecked(),
                hide_periodic=self.hide_periodic_filter.isChecked(),
            )
        except ValueError as exc:
            self.external_message_status.setText(f"Nieprawidłowy filtr: {exc}")
            return

        project_filter_set = None
        if self.apply_project_filters.isChecked():
            if hasattr(self, "stored_apply_filters"):
                self.stored_apply_filters.setChecked(True)
            project_filter_set = self._stored_session_controller.active_filter_set

        has_local = any(
            (
                criteria.protocol,
                criteria.sender,
                criteria.identity_text,
                criteria.time_from_ns is not None,
                criteria.time_to_ns is not None,
                criteria.data_pattern,
                criteria.only_errors,
                criteria.hide_periodic,
            )
        )
        if not has_local and project_filter_set is None:
            self._display_model.set_visible_ids(None)
            self._show_filter_result(self._display_model.total_messages)
            return

        self._local_filter_generation += 1
        generation = self._local_filter_generation
        self.apply_message_filters_button.setEnabled(False)
        self.clear_message_filters_button.setEnabled(False)
        self.external_message_progress.setRange(0, 0)
        self.external_message_progress.setFormat("Filtrowanie…")
        self.external_message_status.setText("Filtrowanie indeksowanego obrazu…")
        task = StoredLogicalSqlFilterTask(
            generation,
            self._display_model.cache_path,
            criteria,
            project_filter_set,
        )
        task.signals.completed.connect(self._message_filters_applied)
        task.signals.failed.connect(self._message_filters_failed)
        self._local_filter_tasks.append(task)
        self._local_filter_tasks = self._local_filter_tasks[-3:]
        QThreadPool.globalInstance().start(task)

    def _message_filters_applied(
        self,
        generation: int,
        identifiers: object,
        total: int,
    ) -> None:
        if generation != self._local_filter_generation:
            return
        visible_ids = tuple(int(value) for value in identifiers)
        self._display_model.set_visible_ids(visible_ids)
        self._show_filter_result(len(visible_ids), total)

    def _show_filter_result(self, visible: int, total: int | None = None) -> None:
        total = self._display_model.total_messages if total is None else int(total)
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(100)
        self.external_message_progress.setFormat("Gotowe — 100%")
        self.external_message_status.setText(
            f"widoczne {visible:,} z {total:,} wiadomości".replace(",", " ")
        )
        self.tabs.setTabText(
            self.message_tab_index,
            f"Wiadomości logiczne ({visible:,}/{total:,})".replace(",", " "),
        )
        self.apply_message_filters_button.setEnabled(True)
        self.clear_message_filters_button.setEnabled(True)

    def _clear_message_filters(self) -> None:
        self._local_filter_generation += 1
        self.protocol_filter.setCurrentIndex(0)
        self.sender_filter.setCurrentIndex(0)
        self.identity_filter.clear()
        self.time_from_filter.clear()
        self.time_to_filter.clear()
        self.data_offset_filter.clear()
        self.data_value_filter.clear()
        self.only_errors_filter.setChecked(False)
        self.hide_periodic_filter.setChecked(False)
        self.apply_project_filters.setChecked(False)
        if hasattr(self, "stored_apply_filters"):
            self.stored_apply_filters.setChecked(False)
        self._display_model.set_visible_ids(None)
        total = self._display_model.total_messages
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(100 if total else 0)
        self.external_message_progress.setFormat(
            "Gotowe — 100%" if total else "Oczekiwanie"
        )
        self.external_message_status.setText(
            f"otwarto zapisany obraz: {total:,} wiadomości".replace(",", " ")
            if total
            else "Brak załadowanych wiadomości"
        )
        self.tabs.setTabText(
            self.message_tab_index,
            f"Wiadomości logiczne ({total:,})".replace(",", " ")
            if total
            else "Wiadomości logiczne",
        )
        self.apply_message_filters_button.setEnabled(True)
        self.clear_message_filters_button.setEnabled(True)

    def _display_message_selected(self) -> None:
        rows = self.message_table.selectionModel().selectedRows()
        if not rows:
            return
        message = self._display_model.message_at(rows[0].row())
        if message is not None:
            self.inspector_text.emit(format_logical_message_inspector(message))

    def shutdown(self) -> None:
        self._display_model.close_cache()
        super().shutdown()
