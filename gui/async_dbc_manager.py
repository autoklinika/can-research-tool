from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QStackedLayout, QVBoxLayout, QWidget

from app.project import CrtProject
from app.project_dbc import list_project_dbc

from .dbc_manager import DbcManagerWidget


class _DbcLoadSignals(QObject):
    loaded = Signal(object)
    failed = Signal(str)


class _DbcLoadTask(QRunnable):
    def __init__(self, project: CrtProject) -> None:
        super().__init__()
        self.project = project
        self.signals = _DbcLoadSignals()

    @Slot()
    def run(self) -> None:
        try:
            records = list_project_dbc(self.project)
        except Exception as exc:  # pragma: no cover - platform/database dependent
            self.signals.failed.emit(str(exc))
            return
        self.signals.loaded.emit(records)


class AsyncDbcManagerWidget(QWidget):
    """Load project DBC metadata outside the Qt GUI thread.

    SQLite can temporarily wait for another project transaction. The previous
    synchronous construction of ``DbcManagerWidget`` therefore made the whole
    application appear frozen. This wrapper keeps the workspace responsive and
    installs the normal manager after metadata is available.
    """

    changed = Signal()
    output_message = Signal(str)
    inspector_text = Signal(str)

    def __init__(self, project: CrtProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.manager: DbcManagerWidget | None = None
        self._task: _DbcLoadTask | None = None
        self._disposed = False

        self._stack = QStackedLayout(self)
        self._loading_page = self._build_loading_page()
        self._stack.addWidget(self._loading_page)
        self._start_loading()

    def _build_loading_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        title = QLabel("Ładowanie dekoderów DBC…", page)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        self.status_label = QLabel(
            "Odczytywanie metadanych projektu odbywa się poza wątkiem interfejsu.",
            page,
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar(page)
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)

        self.retry_button = QPushButton("Spróbuj ponownie", page)
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(self._start_loading)
        layout.addWidget(self.retry_button)
        layout.addStretch(1)
        return page

    def _start_loading(self) -> None:
        if self._disposed or self._task is not None:
            return
        self.status_label.setText(
            "Odczytywanie metadanych projektu odbywa się poza wątkiem interfejsu."
        )
        self.progress.setVisible(True)
        self.retry_button.setVisible(False)

        task = _DbcLoadTask(self.project)
        task.signals.loaded.connect(self._loaded)
        task.signals.failed.connect(self._failed)
        self._task = task
        QThreadPool.globalInstance().start(task)

    @Slot(object)
    def _loaded(self, records: object) -> None:
        self._task = None
        if self._disposed:
            return

        manager = DbcManagerWidget(self.project, records=records, parent=self)
        manager.changed.connect(self.changed)
        manager.output_message.connect(self.output_message)
        manager.inspector_text.connect(self.inspector_text)
        self.manager = manager
        self._stack.addWidget(manager)
        self._stack.setCurrentWidget(manager)
        self._loading_page.deleteLater()

    @Slot(str)
    def _failed(self, message: str) -> None:
        self._task = None
        if self._disposed:
            return
        self.progress.setVisible(False)
        self.status_label.setText(
            "Nie udało się odczytać listy DBC. Interfejs pozostał aktywny.\n\n"
            f"{message}"
        )
        self.retry_button.setVisible(True)
        self.output_message.emit(f"Nie udało się otworzyć Dekoderów DBC: {message}")

    def shutdown(self) -> None:
        self._disposed = True
