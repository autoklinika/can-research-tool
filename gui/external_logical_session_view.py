from __future__ import annotations

import os
import pickle
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QThreadPool, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.logical_records import logical_message_path_for_session

from .logical_message_model import format_logical_message_inspector
from .session_view import SessionViewWidget
from .stored_logical_message_panel import (
    ProtocolBadgeDelegate,
    StoredLogicalCriteria,
    StoredLogicalDisplayModel,
    StoredLogicalFilterTask,
    parse_data_pattern,
    parse_time_filter,
    protocol_label,
    sender_text,
)


class ExternalLogicalSessionViewWidget(SessionViewWidget):
    """Stored-session workspace matching the compact engineering target layout.

    CSV parsing, raw-session reconstruction, decoder execution and local filtering
    remain outside the GUI thread. The visible tab contains only compact controls,
    progress, status and the final eight-column operator table.
    """

    def __init__(
        self,
        *args,
        raw_frame_capacity: int | None = None,
        **kwargs,
    ) -> None:
        if raw_frame_capacity is not None:
            self.MAX_ROWS = max(1, int(raw_frame_capacity))
        super().__init__(*args, **kwargs)

        self._logical_process: QProcess | None = None
        self._logical_result_path: Path | None = None
        self._logical_stdout_buffer = ""
        self._all_logical_messages: tuple[object, ...] = ()
        self._local_filter_generation = 0
        self._local_filter_tasks: list[StoredLogicalFilterTask] = []

        self.header.hide()
        root = self.layout()
        if root is not None:
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

        self._display_model = StoredLogicalDisplayModel(self)
        self._protocol_delegate = ProtocolBadgeDelegate(self.message_table)
        self._build_target_message_workspace()

        self.tabs.setTabText(
            self.message_tab_index,
            "Wiadomości logiczne — kliknij, aby załadować wszystkie",
        )

    def _build_target_message_workspace(self) -> None:
        page = self.tabs.widget(self.message_tab_index)
        if page is None:
            return
        page.setObjectName("storedLogicalWorkspace")
        layout = page.layout()
        if layout is None:
            layout = QVBoxLayout(page)
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.message_table:
                widget.hide()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        self._protocol_summary_label = page.findChild(QLabel, "protocolMessageSummary")
        if self._protocol_summary_label is not None:
            self._protocol_summary_label.hide()

        filter_section = QFrame(page)
        filter_section.setObjectName("logicalFilterSection")
        filter_root = QVBoxLayout(filter_section)
        filter_root.setContentsMargins(0, 0, 0, 0)
        filter_root.setSpacing(0)
        filter_title = QLabel("FILTRY", filter_section)
        filter_title.setObjectName("logicalSectionTitle")
        filter_root.addWidget(filter_title)

        filter_body = QWidget(filter_section)
        filter_body.setObjectName("logicalSectionBody")
        grid = QGridLayout(filter_body)
        grid.setContentsMargins(8, 8, 8, 9)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self.protocol_filter = QComboBox(filter_body)
        self.protocol_filter.setObjectName("logicalProtocolFilter")
        self.protocol_filter.addItem("Wszystkie", "")
        self.protocol_filter.setMinimumWidth(120)

        self.sender_filter = QComboBox(filter_body)
        self.sender_filter.setObjectName("logicalSenderFilter")
        self.sender_filter.addItem("Wszystkie", "")
        self.sender_filter.setMinimumWidth(120)

        self.identity_filter = QLineEdit(filter_body)
        self.identity_filter.setObjectName("logicalIdentityFilter")
        self.identity_filter.setClearButtonEnabled(True)
        self.identity_filter.setMinimumWidth(120)

        self.time_from_filter = QLineEdit(filter_body)
        self.time_from_filter.setObjectName("logicalTimeFromFilter")
        self.time_from_filter.setPlaceholderText("HH:MM:SS.ffffff")
        self.time_from_filter.setMinimumWidth(135)

        self.time_to_filter = QLineEdit(filter_body)
        self.time_to_filter.setObjectName("logicalTimeToFilter")
        self.time_to_filter.setPlaceholderText("HH:MM:SS.ffffff")
        self.time_to_filter.setMinimumWidth(135)

        self.data_offset_filter = QLineEdit(filter_body)
        self.data_offset_filter.setObjectName("logicalDataOffsetFilter")
        self.data_offset_filter.setPlaceholderText("Offset")
        self.data_offset_filter.setMaximumWidth(95)

        self.data_value_filter = QLineEdit(filter_body)
        self.data_value_filter.setObjectName("logicalDataValueFilter")
        self.data_value_filter.setPlaceholderText("np. 22 F1 90 lub 34")
        self.data_value_filter.setMinimumWidth(260)
        self.data_value_filter.setClearButtonEnabled(True)

        self.only_errors_filter = QCheckBox("Tylko błędy", filter_body)
        self.only_errors_filter.setObjectName("logicalOnlyErrorsFilter")
        self.hide_periodic_filter = QCheckBox("Ukryj okresowe", filter_body)
        self.hide_periodic_filter.setObjectName("logicalHidePeriodicFilter")

        self.apply_message_filters_button = QPushButton("Zastosuj", filter_body)
        self.apply_message_filters_button.setObjectName("applyLogicalFilters")
        self.apply_message_filters_button.setMinimumWidth(96)
        self.apply_message_filters_button.clicked.connect(self._apply_message_filters)

        self.clear_message_filters_button = QPushButton("Wyczyść", filter_body)
        self.clear_message_filters_button.setObjectName("clearLogicalFilters")
        self.clear_message_filters_button.setMinimumWidth(96)
        self.clear_message_filters_button.clicked.connect(self._clear_message_filters)

        grid.addWidget(QLabel("Protokoły:", filter_body), 0, 0)
        grid.addWidget(self.protocol_filter, 0, 1)
        grid.addWidget(QLabel("Nadawca:", filter_body), 0, 2)
        grid.addWidget(self.sender_filter, 0, 3)
        grid.addWidget(QLabel("ID / Nazwa:", filter_body), 0, 4)
        grid.addWidget(self.identity_filter, 0, 5)
        grid.addWidget(QLabel("Czas od:", filter_body), 0, 6)
        grid.addWidget(self.time_from_filter, 0, 7)
        grid.addWidget(QLabel("Czas do:", filter_body), 0, 8)
        grid.addWidget(self.time_to_filter, 0, 9)
        grid.addWidget(self.apply_message_filters_button, 0, 10)
        grid.addWidget(self.clear_message_filters_button, 0, 11)

        grid.addWidget(QLabel("Dane (hex/dec):", filter_body), 1, 0)
        grid.addWidget(self.data_offset_filter, 1, 1)
        grid.addWidget(self.data_value_filter, 1, 2, 1, 4)
        grid.addWidget(self.only_errors_filter, 1, 6)
        grid.addWidget(self.hide_periodic_filter, 1, 7, 1, 2)
        grid.setColumnStretch(5, 1)
        grid.setColumnStretch(9, 1)
        filter_root.addWidget(filter_body)
        layout.addWidget(filter_section)

        loading_section = QFrame(page)
        loading_section.setObjectName("logicalLoadingSection")
        loading_root = QVBoxLayout(loading_section)
        loading_root.setContentsMargins(0, 0, 0, 0)
        loading_root.setSpacing(0)
        loading_title = QLabel("ŁADOWANIE WIADOMOŚCI LOGICZNYCH", loading_section)
        loading_title.setObjectName("logicalSectionTitle")
        loading_root.addWidget(loading_title)

        loading_body = QWidget(loading_section)
        loading_body.setObjectName("logicalSectionBody")
        loading_row = QHBoxLayout(loading_body)
        loading_row.setContentsMargins(8, 8, 8, 8)
        loading_row.setSpacing(14)

        self.external_message_progress = QProgressBar(loading_body)
        self.external_message_progress.setObjectName("logicalLoadProgress")
        self.external_message_progress.setTextVisible(True)
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(0)
        self.external_message_progress.setFormat("Oczekiwanie")
        self.external_message_progress.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.external_message_status = QLabel(
            "Kliknij zakładkę, aby załadować wszystkie wiadomości logiczne.",
            loading_body,
        )
        self.external_message_status.setObjectName("logicalLoadStatus")
        self.external_message_status.setMinimumWidth(280)
        self.external_message_status.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self.external_message_button = QPushButton("Załaduj ponownie", loading_body)
        self.external_message_button.setObjectName("reloadLogicalMessages")
        self.external_message_button.setMinimumWidth(106)
        self.external_message_button.clicked.connect(self._start_embedded_load)

        loading_row.addWidget(self.external_message_progress, 5)
        loading_row.addWidget(self.external_message_status, 2)
        loading_row.addWidget(self.external_message_button)
        loading_root.addWidget(loading_body)
        layout.addWidget(loading_section)

        self.message_table.setObjectName("storedLogicalMessageTable")
        self.message_table.setModel(self._display_model)
        self.message_table.setItemDelegateForColumn(4, self._protocol_delegate)
        self.message_table.setAlternatingRowColors(False)
        self.message_table.setShowGrid(True)
        self.message_table.setWordWrap(False)
        self.message_table.verticalHeader().hide()
        self.message_table.verticalHeader().setDefaultSectionSize(33)
        self.message_table.horizontalHeader().setMinimumSectionSize(44)
        self.message_table.horizontalHeader().setStretchLastSection(True)
        self.message_table.setColumnWidth(0, 125)
        self.message_table.setColumnWidth(1, 115)
        self.message_table.setColumnWidth(2, 120)
        self.message_table.setColumnWidth(3, 115)
        self.message_table.setColumnWidth(4, 95)
        self.message_table.setColumnWidth(5, 55)
        self.message_table.setColumnWidth(6, 230)
        self.message_table.selectionModel().selectionChanged.connect(
            self._display_message_selected
        )
        self.message_table.hide()
        layout.addWidget(self.message_table, 1)

    def _session_tab_changed(self, index: int) -> None:
        if (
            index == self.message_tab_index
            and not self._message_loading
            and not self._messages_ready
        ):
            self._start_embedded_load()

    def _start_message_load(self) -> None:
        self._start_embedded_load()

    def reload_logical_messages(self, dbc_paths: tuple[Path, ...]) -> None:
        self._dbc_paths = tuple(Path(item) for item in dbc_paths)
        self._stop_logical_process()
        self._messages_ready = False
        self._message_loading = False
        self._all_logical_messages = ()
        self.message_model.clear()
        self._display_model.clear()
        self.message_table.hide()
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(0)
        self.external_message_progress.setFormat("Oczekiwanie")
        self.external_message_status.setText(
            "Dekodery zostały zmienione. Wiadomości zostaną zbudowane ponownie."
        )
        self.tabs.setTabText(
            self.message_tab_index,
            "Wiadomości logiczne — kliknij, aby załadować wszystkie",
        )
        if self.tabs.currentIndex() == self.message_tab_index:
            self._start_embedded_load()

    def _start_embedded_load(self) -> None:
        if self._message_loading:
            return

        message_path = logical_message_path_for_session(self.path)
        self._stop_logical_process()
        self._cleanup_result_file()

        descriptor, result_name = tempfile.mkstemp(
            prefix="crt-logical-",
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

        self._message_load_generation += 1
        self._message_loading = True
        self._messages_ready = False
        self._all_logical_messages = ()
        self.message_model.clear()
        self._display_model.clear()
        self.message_table.hide()
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(0)
        self.external_message_progress.setFormat("Ładowanie — 0%")
        status_source = (
            message_path.name
            if message_path.is_file()
            else f"{self.path.name} — rekonstrukcja z surowych ramek"
        )
        self.external_message_status.setText(
            f"Ładowanie wszystkich wiadomości z {status_source}…"
        )
        self.tabs.setTabText(
            self.message_tab_index,
            "Wiadomości logiczne — ładowanie…",
        )
        process.start(sys.executable, arguments)

    def _consume_process_stdout(self) -> None:
        process = self._logical_process
        if process is None:
            return
        chunk = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._logical_stdout_buffer += chunk
        while "\n" in self._logical_stdout_buffer:
            line, self._logical_stdout_buffer = self._logical_stdout_buffer.split("\n", 1)
            self._handle_process_line(line.rstrip("\r"))

    def _handle_process_line(self, line: str) -> None:
        if line.startswith("STATUS\t"):
            self.external_message_status.setText(line.partition("\t")[2])
        elif line.startswith("PROGRESS\t"):
            value_text = line.partition("\t")[2].strip()
            try:
                value = max(0, min(100, int(value_text)))
            except ValueError:
                return
            self.external_message_progress.setRange(0, 100)
            self.external_message_progress.setValue(value)
            self.external_message_progress.setFormat(f"Ładowanie — {value}%")
        elif line.startswith("RESULT\t"):
            result_text = line.partition("\t")[2].strip()
            if result_text:
                self._logical_result_path = Path(result_text)

    def _logical_process_finished(self, exit_code: int, exit_status) -> None:
        process = self._logical_process
        if process is None:
            return

        self._consume_process_stdout()
        if self._logical_stdout_buffer.strip():
            self._handle_process_line(self._logical_stdout_buffer.strip())
        self._logical_stdout_buffer = ""

        error_text = bytes(process.readAllStandardError()).decode(
            "utf-8",
            errors="replace",
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
            self._show_load_failure("proces nie utworzył pliku wynikowego")
            self._cleanup_result_file()
            return

        try:
            with result_path.open("rb") as handle:
                result = pickle.load(handle)
            messages = list(result["messages"])
            total_messages = int(result["total"])
            source = str(result["source"])
            path = str(result["path"])
        except (OSError, KeyError, TypeError, ValueError, pickle.PickleError) as exc:
            self._show_load_failure(f"nie można odczytać wyniku: {exc}")
            self._cleanup_result_file()
            return

        if len(messages) != total_messages:
            self._show_load_failure(
                f"załadowano {len(messages)} z {total_messages} wiadomości"
            )
            self._cleanup_result_file()
            return

        self.message_model._capacity = max(1, len(messages))
        self.message_model.replace_messages(messages)
        self._all_logical_messages = tuple(messages)
        self._display_model.replace_messages(messages)
        self._populate_filter_choices(messages)
        self.message_table.show()

        self._message_loading = False
        self._messages_ready = True
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(100)
        self.external_message_progress.setFormat("Gotowe — 100%")
        self.external_message_status.setText(
            f"załadowano wszystkie {total_messages:,} wiadomości".replace(",", " ")
        )
        self.tabs.setTabText(
            self.message_tab_index,
            f"Wiadomości logiczne ({total_messages:,})".replace(",", " "),
        )
        source_text = "messages.csv" if source.startswith("messages-csv") else source
        if source.endswith("+dbc"):
            source_text += " + DBC"
        self.output_message.emit(
            f"Wiadomości logiczne {path}: załadowano wszystkie "
            f"{total_messages} ({source_text})"
        )
        self._cleanup_result_file()

    def _populate_filter_choices(self, messages: list[object]) -> None:
        selected_protocol = self.protocol_filter.currentData() or ""
        selected_sender = self.sender_filter.currentData() or ""
        protocols = sorted(
            {
                (protocol_label(getattr(message, "protocol", "unknown")), str(getattr(message, "protocol", "unknown")))
                for message in messages
            },
            key=lambda item: item[0].casefold(),
        )
        senders = sorted(
            {sender_text(message) for message in messages if sender_text(message) != "—"},
            key=str.casefold,
        )

        self.protocol_filter.blockSignals(True)
        self.protocol_filter.clear()
        self.protocol_filter.addItem("Wszystkie", "")
        for label, value in protocols:
            self.protocol_filter.addItem(label, value)
        protocol_index = self.protocol_filter.findData(selected_protocol)
        self.protocol_filter.setCurrentIndex(max(0, protocol_index))
        self.protocol_filter.blockSignals(False)

        self.sender_filter.blockSignals(True)
        self.sender_filter.clear()
        self.sender_filter.addItem("Wszystkie", "")
        for sender in senders:
            self.sender_filter.addItem(sender, sender)
        sender_index = self.sender_filter.findData(selected_sender)
        self.sender_filter.setCurrentIndex(max(0, sender_index))
        self.sender_filter.blockSignals(False)

    def _apply_message_filters(self) -> None:
        if not self._messages_ready:
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

        available = self._stored_session_controller.available_filter_set.active_count
        if available and hasattr(self, "stored_apply_filters"):
            self.stored_apply_filters.setChecked(True)
        project_filter_set = (
            self._stored_session_controller.active_filter_set
            if getattr(self, "stored_apply_filters", None) is not None
            and self.stored_apply_filters.isChecked()
            else None
        )

        self._local_filter_generation += 1
        generation = self._local_filter_generation
        self.apply_message_filters_button.setEnabled(False)
        self.clear_message_filters_button.setEnabled(False)
        self.external_message_progress.setRange(0, 0)
        self.external_message_progress.setFormat("Filtrowanie…")
        self.external_message_status.setText(
            f"Filtrowanie {len(self._all_logical_messages):,} wiadomości…".replace(",", " ")
        )
        task = StoredLogicalFilterTask(
            generation,
            self._all_logical_messages,
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
        messages: object,
        total: int,
    ) -> None:
        if generation != self._local_filter_generation:
            return
        visible = list(messages)
        self._display_model.replace_messages(visible)
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(100)
        self.external_message_progress.setFormat("Gotowe — 100%")
        self.external_message_status.setText(
            f"widoczne {len(visible):,} z {total:,} wiadomości".replace(",", " ")
        )
        self.tabs.setTabText(
            self.message_tab_index,
            f"Wiadomości logiczne ({len(visible):,}/{total:,})".replace(",", " "),
        )
        self.apply_message_filters_button.setEnabled(True)
        self.clear_message_filters_button.setEnabled(True)

    def _message_filters_failed(self, generation: int, error: str) -> None:
        if generation != self._local_filter_generation:
            return
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(0)
        self.external_message_progress.setFormat("Błąd")
        self.external_message_status.setText(f"Błąd filtrowania: {error}")
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
        if hasattr(self, "stored_apply_filters"):
            self.stored_apply_filters.setChecked(False)
        self._display_model.replace_messages(self._all_logical_messages)
        total = len(self._all_logical_messages)
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(100 if total else 0)
        self.external_message_progress.setFormat(
            "Gotowe — 100%" if total else "Oczekiwanie"
        )
        self.external_message_status.setText(
            f"załadowano wszystkie {total:,} wiadomości".replace(",", " ")
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

    def _logical_process_error(self, process_error) -> None:
        process = self._logical_process
        if process is None:
            return
        if process_error == QProcess.ProcessError.FailedToStart:
            process.deleteLater()
            self._logical_process = None
            self._show_load_failure("nie udało się uruchomić procesu pomocniczego")
            self._cleanup_result_file()

    def _show_load_failure(self, detail: str) -> None:
        self._message_loading = False
        self._messages_ready = False
        self.message_table.hide()
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(0)
        self.external_message_progress.setFormat("Błąd")
        self.external_message_status.setText(
            f"Nie udało się załadować wiadomości logicznych: {detail}"
        )
        self.tabs.setTabText(
            self.message_tab_index,
            "Wiadomości logiczne — błąd",
        )

    def _stop_logical_process(self) -> None:
        process = self._logical_process
        if process is None:
            return
        process.blockSignals(True)
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
            process.waitForFinished(500)
        process.deleteLater()
        self._logical_process = None
        self._message_loading = False

    def _cleanup_result_file(self) -> None:
        result_path = self._logical_result_path
        self._logical_result_path = None
        if result_path is None:
            return
        try:
            result_path.unlink(missing_ok=True)
            result_path.with_suffix(result_path.suffix + ".tmp").unlink(
                missing_ok=True
            )
        except OSError:
            pass

    def shutdown(self) -> None:
        self._local_filter_generation += 1
        self._stop_logical_process()
        self._cleanup_result_file()
        super().shutdown()
