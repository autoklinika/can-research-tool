from __future__ import annotations

import os
import pickle
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton

from app.logical_records import logical_message_path_for_session

from .session_view import SessionViewWidget


class ExternalLogicalSessionViewWidget(SessionViewWidget):
    """Stored-session view with isolated full loading inside the normal tab.

    The helper process performs CSV parsing or raw-session reconstruction and
    protocol decoding outside the main GUI process. The user remains in the
    session tab: progress is displayed while the worker runs, then the complete
    logical-message set is placed in the existing table.
    """

    def __init__(
        self,
        *args,
        raw_frame_capacity: int | None = None,
        **kwargs,
    ) -> None:
        if raw_frame_capacity is not None:
            # SessionViewWidget reads this instance attribute while constructing
            # the stored raw-frame model. Live capture models remain bounded.
            self.MAX_ROWS = max(1, int(raw_frame_capacity))
        super().__init__(*args, **kwargs)

        self._logical_process: QProcess | None = None
        self._logical_result_path: Path | None = None
        self._logical_stdout_buffer = ""

        page = self.message_table.parentWidget()
        layout = page.layout() if page is not None else None

        self.message_table.hide()
        self._protocol_summary_label = (
            page.findChild(QLabel, "protocolMessageSummary") if page is not None else None
        )
        if self._protocol_summary_label is not None:
            self._protocol_summary_label.hide()

        self.external_message_status = QLabel(
            "Kliknij zakładkę, aby załadować wszystkie wiadomości logiczne."
        )
        self.external_message_status.setWordWrap(True)

        self.external_message_progress = QProgressBar()
        self.external_message_progress.setTextVisible(True)
        self.external_message_progress.hide()

        self.external_message_button = QPushButton("Załaduj ponownie")
        self.external_message_button.clicked.connect(self._start_embedded_load)
        self.external_message_button.hide()

        if layout is not None:
            layout.insertWidget(0, self.external_message_status)
            layout.insertWidget(1, self.external_message_progress)
            layout.insertWidget(2, self.external_message_button)

        self.tabs.setTabText(
            self.message_tab_index,
            "Wiadomości logiczne — kliknij, aby załadować wszystkie",
        )

    def _session_tab_changed(self, index: int) -> None:
        if (
            index == self.message_tab_index
            and not self._message_loading
            and not self._messages_ready
        ):
            self._start_embedded_load()

    def _start_message_load(self) -> None:
        """Compatibility hook used by the base session view."""

        self._start_embedded_load()

    def reload_logical_messages(self, dbc_paths: tuple[Path, ...]) -> None:
        self._dbc_paths = tuple(Path(item) for item in dbc_paths)
        self._stop_logical_process()
        self._messages_ready = False
        self._message_loading = False
        self.message_model.clear()
        self.message_table.hide()
        if self._protocol_summary_label is not None:
            self._protocol_summary_label.hide()
        self.external_message_progress.hide()
        self.external_message_button.hide()
        self.external_message_status.setText(
            "Dekodery zostały zmienione. Wszystkie wiadomości zostaną załadowane ponownie."
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
        self.message_model.clear()
        self.message_table.hide()
        if self._protocol_summary_label is not None:
            self._protocol_summary_label.hide()
        self.external_message_button.hide()
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(0)
        self.external_message_progress.setFormat("Ładowanie — 0%")
        self.external_message_progress.show()
        if message_path.is_file():
            status_source = message_path.name
        else:
            status_source = f"{self.path.name} — rekonstrukcja z surowych ramek"
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
            line, self._logical_stdout_buffer = self._logical_stdout_buffer.split(
                "\n",
                1,
            )
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

        # This model belongs to the stored-session view, not the bounded live
        # preview. Expand its retained capacity to the exact completed result.
        self.message_model._capacity = max(1, len(messages))
        self.message_model.replace_messages(messages)
        self.message_table.show()
        if self._protocol_summary_label is not None:
            self._protocol_summary_label.show()

        self._message_loading = False
        self._messages_ready = True
        self.external_message_progress.setRange(0, 100)
        self.external_message_progress.setValue(100)
        self.external_message_progress.setFormat("Gotowe — 100%")
        self.external_message_progress.show()
        self.external_message_button.setText("Załaduj ponownie")
        self.external_message_button.show()

        source_text = "messages.csv" if source.startswith("messages-csv") else source
        if source.endswith("+dbc"):
            source_text += " + DBC"
        self.external_message_status.setText(
            (
                f"Sesja: {path} | załadowano wszystkie {total_messages:,} wiadomości "
                f"| źródło: {source_text}"
            ).replace(",", " ")
        )
        self.tabs.setTabText(
            self.message_tab_index,
            f"Wiadomości logiczne ({total_messages:,})".replace(",", " "),
        )
        self.output_message.emit(
            f"Wiadomości logiczne {path}: załadowano wszystkie {total_messages} ({source_text})"
        )
        self._cleanup_result_file()

    def _logical_process_error(self, process_error) -> None:
        process = self._logical_process
        if process is None:
            return
        if process_error == QProcess.ProcessError.FailedToStart:
            process.deleteLater()
            self._logical_process = None
            self._show_load_failure(
                "nie udało się uruchomić procesu pomocniczego"
            )
            self._cleanup_result_file()

    def _show_load_failure(self, detail: str) -> None:
        self._message_loading = False
        self._messages_ready = False
        self.message_table.hide()
        if self._protocol_summary_label is not None:
            self._protocol_summary_label.hide()
        self.external_message_progress.hide()
        self.external_message_button.setText("Ponów ładowanie")
        self.external_message_button.show()
        self.external_message_status.setText(
            f"Nie udało się załadować wiadomości logicznych:\n{detail}"
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
        self._stop_logical_process()
        self._cleanup_result_file()
        super().shutdown()
