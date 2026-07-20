from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton

from app.logical_records import logical_message_path_for_session

from .session_view import SessionViewWidget


class ExternalLogicalSessionViewWidget(SessionViewWidget):
    """Stored-session view that keeps logical-message work outside the main GUI.

    The raw-frame and marker tabs remain unchanged. The logical-message tab acts
    as a lightweight launcher for a dedicated process reading the existing
    ``*.messages.csv`` sidecar. A slow decoder or a damaged Qt item view can no
    longer block capture, project navigation or the main application event loop.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # The base widget creates the table and connects tab-change signals to
        # this class' overridden no-op handler. Keep the page lightweight and
        # expose an explicit external-viewer action instead of loading on click.
        self.message_table.hide()
        page = self.message_table.parentWidget()
        layout = page.layout() if page is not None else None

        self.external_message_status = QLabel(
            "Wiadomości logiczne są otwierane w osobnym procesie CRT.\n"
            "Główna aplikacja pozostaje responsywna także dla bardzo dużych sesji."
        )
        self.external_message_status.setWordWrap(True)

        self.external_message_button = QPushButton("Otwórz wiadomości logiczne")
        self.external_message_button.clicked.connect(self._open_external_viewer)

        if layout is not None:
            layout.insertWidget(0, self.external_message_status)
            layout.insertWidget(1, self.external_message_button)

        self.tabs.setTabText(self.message_tab_index, "Wiadomości logiczne")

    def _session_tab_changed(self, index: int) -> None:
        # Deliberately do not call SessionViewWidget._start_message_load().
        # The tab itself is now only a launcher for the isolated viewer.
        return

    def reload_logical_messages(self, dbc_paths: tuple[Path, ...]) -> None:
        self._dbc_paths = tuple(Path(item) for item in dbc_paths)
        self.message_model.clear()
        self.tabs.setTabText(self.message_tab_index, "Wiadomości logiczne")

    def _open_external_viewer(self) -> None:
        message_path = logical_message_path_for_session(self.path)
        if not message_path.is_file():
            QMessageBox.information(
                self,
                "Wiadomości logiczne",
                "Dla tej sesji nie istnieje jeszcze zewnętrzny plik messages.csv. "
                "Sesja pozostaje dostępna w zakładce surowych ramek.",
            )
            return

        script_path = Path(__file__).resolve().parent.parent / "crt_logical_messages.py"
        arguments = [str(script_path), str(self.path)]
        for dbc_path in self._dbc_paths:
            arguments.extend(("--dbc", str(dbc_path)))

        started = QProcess.startDetached(sys.executable, arguments)
        if isinstance(started, tuple):
            ok = bool(started[0])
        else:
            ok = bool(started)
        if not ok:
            QMessageBox.critical(
                self,
                "Wiadomości logiczne",
                "Nie udało się uruchomić zewnętrznego przeglądarki wiadomości.",
            )
            return

        self.external_message_status.setText(
            f"Uruchomiono osobny przegląd dla:\n{message_path.name}"
        )
