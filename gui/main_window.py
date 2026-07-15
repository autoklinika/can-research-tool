from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QThreadPool, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.project import CrtProject

from .import_task import ProjectImportTask
from .live_capture import LiveCaptureWidget
from .project_dialog import NewProjectDialog
from .project_explorer import ProjectExplorer
from .project_overview import ProjectOverviewWidget
from .session_view import SessionViewWidget
from .study_area_view import StudyAreaViewWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CAN Research Tool")
        self.resize(1580, 920)
        self.setMinimumSize(1100, 700)

        self.settings = QSettings()
        self.project: CrtProject | None = None
        self._import_tasks: list[ProjectImportTask] = []
        self._tab_keys: dict[str, QWidget] = {}

        self._build_actions()
        self._build_menu()
        self._build_activity_bar()
        self._build_docks()
        self._build_central_tabs()
        self._build_status_bar()
        self._show_welcome()

        last_project = self.settings.value("project/lastPath", "", str)
        if last_project and (Path(last_project) / "project.crt.json").is_file():
            try:
                self._open_project_path(Path(last_project))
            except Exception as exc:
                self._append_output(f"Nie udało się automatycznie otworzyć projektu: {exc}")

    def _build_actions(self) -> None:
        self.new_project_action = QAction("Nowy projekt…", self)
        self.new_project_action.setShortcut("Ctrl+Shift+N")
        self.new_project_action.triggered.connect(self._new_project)

        self.open_project_action = QAction("Otwórz projekt…", self)
        self.open_project_action.setShortcut("Ctrl+Shift+O")
        self.open_project_action.triggered.connect(self._open_project_dialog)

        self.import_action = QAction("Importuj log…", self)
        self.import_action.setShortcut("Ctrl+I")
        self.import_action.triggered.connect(self._import_log)
        self.import_action.setEnabled(False)

        self.exit_action = QAction("Zakończ", self)
        self.exit_action.triggered.connect(self.close)

        self.toggle_explorer_action = QAction("Projekt", self)
        self.toggle_explorer_action.setCheckable(True)
        self.toggle_explorer_action.setChecked(True)
        self.toggle_explorer_action.triggered.connect(self._toggle_explorer)

        self.live_action = QAction("Live", self)
        self.live_action.triggered.connect(self._open_live_capture)
        self.search_action = QAction("Szukaj", self)
        self.search_action.triggered.connect(
            lambda: self._open_placeholder("search", "Wyszukiwanie", "Wyszukiwanie po całym projekcie")
        )
        self.compare_action = QAction("Porównaj", self)
        self.compare_action.triggered.connect(
            lambda: self._open_placeholder("compare", "Porównania", "Porównywanie sesji i zdarzeń")
        )
        self.signals_action = QAction("Sygnały", self)
        self.signals_action.triggered.connect(
            lambda: self._open_placeholder("signals", "Sygnały", "Katalog sygnałów i hipotez")
        )
        self.decoders_action = QAction("Dekodery", self)
        self.decoders_action.triggered.connect(
            lambda: self._open_placeholder("decoders", "Dekodery", "Reguły autorskie, J1939 i UDS")
        )
        self.settings_action = QAction("Ustawienia", self)
        self.settings_action.triggered.connect(
            lambda: self._open_placeholder("settings", "Ustawienia", "Ustawienia projektu i aplikacji")
        )

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Plik")
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addSeparator()
        file_menu.addAction(self.import_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        view_menu = self.menuBar().addMenu("Widok")
        view_menu.addAction(self.toggle_explorer_action)

    def _build_activity_bar(self) -> None:
        toolbar = QToolBar("Aktywność", self)
        toolbar.setObjectName("activityBar")
        toolbar.setOrientation(Qt.Vertical)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        toolbar.addAction(self.toggle_explorer_action)
        toolbar.addAction(self.live_action)
        toolbar.addSeparator()
        toolbar.addAction(self.search_action)
        toolbar.addAction(self.compare_action)
        toolbar.addAction(self.signals_action)
        toolbar.addAction(self.decoders_action)
        toolbar.addSeparator()
        toolbar.addAction(self.settings_action)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        self.activity_bar = toolbar

    def _build_docks(self) -> None:
        self.explorer = ProjectExplorer()
        self.explorer.open_overview.connect(self._open_overview)
        self.explorer.open_live_capture.connect(self._open_live_capture)
        self.explorer.open_session.connect(self._open_session)
        self.explorer.open_area.connect(self._open_area)
        self.explorer.import_requested.connect(self._import_log)
        self.explorer.add_area_requested.connect(self._add_study_area)
        self.explorer_dock = QDockWidget("Projekt", self)
        self.explorer_dock.setObjectName("projectExplorerDock")
        self.explorer_dock.setWidget(self.explorer)
        self.explorer_dock.setMinimumWidth(260)
        self.explorer_dock.visibilityChanged.connect(
            self.toggle_explorer_action.setChecked
        )
        self.addDockWidget(Qt.LeftDockWidgetArea, self.explorer_dock)

        self.inspector = QPlainTextEdit()
        self.inspector.setReadOnly(True)
        self.inspector.setMaximumBlockCount(1000)
        self.inspector.setPlaceholderText("Zaznacz ramkę, wiadomość, znacznik lub element projektu.")
        self.inspector_dock = QDockWidget("Inspektor", self)
        self.inspector_dock.setObjectName("inspectorDock")
        self.inspector_dock.setWidget(self.inspector)
        self.inspector_dock.setMinimumWidth(300)
        self.addDockWidget(Qt.RightDockWidgetArea, self.inspector_dock)

        output_tabs = QTabWidget()
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(5000)
        output_tabs.addTab(self.output, "Output")
        problems = QPlainTextEdit()
        problems.setReadOnly(True)
        problems.setPlaceholderText("Błędy parserów, niekompletne transporty i konflikty reguł.")
        output_tabs.addTab(problems, "Problemy")
        tasks = QPlainTextEdit()
        tasks.setReadOnly(True)
        tasks.setPlaceholderText("Postęp indeksowania, importu i analiz.")
        output_tabs.addTab(tasks, "Zadania")
        self.output_dock = QDockWidget("Panel", self)
        self.output_dock.setObjectName("outputDock")
        self.output_dock.setWidget(output_tabs)
        self.output_dock.setMinimumHeight(150)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.output_dock)

    def _build_central_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)

    def _build_status_bar(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)
        self.project_status = QLabel("Brak projektu")
        self.capture_status = QLabel("STOPPED")
        status.addWidget(self.project_status, 1)
        status.addPermanentWidget(self.capture_status)

    def _show_welcome(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(60, 60, 60, 60)
        layout.addStretch(1)
        title = QLabel("CAN Research Tool")
        font = title.font()
        font.setPointSize(font.pointSize() + 14)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        layout.addWidget(
            QLabel(
                "Projektowe środowisko reverse engineeringu CAN.\n"
                "Każdy projekt jest samodzielnym folderem z sesjami, znacznikami, "
                "obszarami badań i wiedzą techniczną."
            )
        )
        row = QHBoxLayout()
        new_button = QPushButton("Nowy projekt")
        new_button.clicked.connect(self._new_project)
        row.addWidget(new_button)
        open_button = QPushButton("Otwórz projekt")
        open_button.clicked.connect(self._open_project_dialog)
        row.addWidget(open_button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(2)
        self._add_tab("welcome", widget, "Start", closable=False)
        self.explorer_dock.hide()
        self.inspector_dock.hide()

    def _new_project(self) -> None:
        dialog = NewProjectDialog(self)
        if dialog.exec() != dialog.Accepted:
            return
        try:
            project = CrtProject.create(
                dialog.project_root(),
                name=dialog.project_name(),
                description=dialog.description(),
                default_bitrate=dialog.bitrate(),
                default_receive_mode=dialog.receive_mode(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Nie można utworzyć projektu", str(exc))
            return
        self._set_project(project)
        self._append_output(f"Utworzono projekt: {project.root}")

    def _open_project_dialog(self) -> None:
        start = self.settings.value("project/lastParent", str(Path.home()), str)
        directory = QFileDialog.getExistingDirectory(self, "Otwórz projekt CRT", start)
        if directory:
            try:
                self._open_project_path(Path(directory))
            except Exception as exc:
                QMessageBox.critical(self, "Nie można otworzyć projektu", str(exc))

    def _open_project_path(self, path: Path) -> None:
        self._set_project(CrtProject.open(path))
        self._append_output(f"Otwarto projekt: {path}")

    def _set_project(self, project: CrtProject) -> None:
        if self._has_active_capture():
            QMessageBox.warning(
                self,
                "CRT",
                "Zatrzymaj aktywną rejestrację przed zmianą projektu.",
            )
            return
        self.project = project
        self.settings.setValue("project/lastPath", str(project.root))
        self.settings.setValue("project/lastParent", str(project.root.parent))
        self.setWindowTitle(f"{project.manifest.name} — CAN Research Tool")
        self.project_status.setText(f"Projekt: {project.manifest.name} | {project.root}")
        self.import_action.setEnabled(True)
        self.explorer.set_project(project)
        self.explorer_dock.show()
        self.inspector_dock.show()
        self._close_project_tabs()
        self._open_overview()

    def _open_overview(self) -> None:
        if self.project is None:
            return
        key = "project-overview"
        existing = self._activate_tab(key)
        if existing:
            return
        widget = ProjectOverviewWidget(self.project)
        widget.open_live_requested.connect(self._open_live_capture)
        widget.add_area_requested.connect(self._add_study_area)
        widget.import_requested.connect(self._import_log)
        self._add_tab(key, widget, "Przegląd")

    def _open_live_capture(self) -> None:
        if self.project is None:
            QMessageBox.information(self, "CRT", "Najpierw otwórz lub utwórz projekt.")
            return
        key = "live-capture"
        if self._activate_tab(key):
            return
        widget = LiveCaptureWidget(self.project)
        widget.inspector_text.connect(self.inspector.setPlainText)
        widget.output_message.connect(self._append_output)
        widget.status_text.connect(self.capture_status.setText)
        widget.project_changed.connect(self.explorer.refresh)
        self._add_tab(key, widget, "Live Capture")

    def _open_session(self, path: str) -> None:
        session_path = Path(path).resolve()
        key = f"session:{session_path}"
        if self._activate_tab(key):
            return
        widget = SessionViewWidget(session_path)
        widget.inspector_text.connect(self.inspector.setPlainText)
        widget.output_message.connect(self._append_output)
        self._add_tab(key, widget, session_path.name.removesuffix(".crt.jsonl"))

    def _open_area(self, area_id: str) -> None:
        if self.project is None:
            return
        area = next(
            (item for item in self.project.list_study_areas() if item.id == area_id),
            None,
        )
        if area is None:
            return
        key = f"area:{area.id}"
        if self._activate_tab(key):
            return
        self._add_tab(key, StudyAreaViewWidget(self.project, area.id), area.name)

    def _add_study_area(self) -> None:
        if self.project is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Nowy obszar badań",
            "Nazwa, np. EGR, VGT, SCR:",
        )
        if not accepted or not name.strip():
            return
        try:
            area = self.project.add_study_area(name)
        except Exception as exc:
            QMessageBox.critical(self, "Nie można dodać obszaru", str(exc))
            return
        self.explorer.refresh()
        self._open_area(area.id)
        self._append_output(f"Dodano obszar badań: {area.name}")

    def _import_log(self) -> None:
        if self.project is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Importuj logi do projektu",
            str(Path.home()),
            "Logi CRT/Kvaser (*.crt.jsonl *.csv);;Sesje CRT (*.crt.jsonl);;CSV (*.csv)",
        )
        for path in paths:
            task = ProjectImportTask(self.project, path)
            task.signals.completed.connect(self._import_completed)
            task.signals.failed.connect(self._import_failed)
            self._import_tasks.append(task)
            QThreadPool.globalInstance().start(task)
            self._append_output(f"Import rozpoczęty: {path}")

    def _import_completed(self, source: str, target: str) -> None:
        self._append_output(f"Import zakończony: {source} → {target}")
        self.explorer.refresh()
        self._open_session(target)
        self._discard_finished_import_tasks()

    def _import_failed(self, source: str, error: str) -> None:
        self._append_output(f"Błąd importu {source}: {error}")
        QMessageBox.critical(self, "Błąd importu", f"{source}\n\n{error}")
        self._discard_finished_import_tasks()

    def _discard_finished_import_tasks(self) -> None:
        self._import_tasks = [task for task in self._import_tasks if not task.autoDelete()]
        # QRunnable ownership is handled by QThreadPool; keeping no stale references is enough.
        self._import_tasks.clear()

    def _open_placeholder(self, key: str, title: str, description: str) -> None:
        if self.project is None:
            return
        if self._activate_tab(key):
            return
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        heading = QLabel(title)
        font = heading.font()
        font.setPointSize(font.pointSize() + 7)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        layout.addWidget(QLabel(description))
        layout.addWidget(QLabel("Moduł został przewidziany w architekturze projektu i będzie rozwijany etapami."))
        layout.addStretch(1)
        self._add_tab(key, widget, title)

    def _add_tab(self, key: str, widget: QWidget, title: str, *, closable: bool = True) -> None:
        widget.setProperty("crtTabKey", key)
        index = self.tabs.addTab(widget, title)
        self._tab_keys[key] = widget
        self.tabs.setCurrentIndex(index)
        if not closable:
            self.tabs.tabBar().setTabButton(index, self.tabs.tabBar().RightSide, None)

    def _activate_tab(self, key: str) -> bool:
        widget = self._tab_keys.get(key)
        if widget is None:
            return False
        index = self.tabs.indexOf(widget)
        if index < 0:
            self._tab_keys.pop(key, None)
            return False
        self.tabs.setCurrentIndex(index)
        return True

    def _close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is None:
            return
        if isinstance(widget, LiveCaptureWidget) and widget.is_capturing:
            QMessageBox.information(
                self,
                "CRT",
                "Zatrzymaj rejestrację przed zamknięciem zakładki Live Capture.",
            )
            return
        key = str(widget.property("crtTabKey") or "")
        if isinstance(widget, LiveCaptureWidget):
            widget.shutdown()
        self.tabs.removeTab(index)
        if key:
            self._tab_keys.pop(key, None)
        widget.deleteLater()

    def _close_project_tabs(self) -> None:
        for index in range(self.tabs.count() - 1, -1, -1):
            widget = self.tabs.widget(index)
            if widget is None:
                continue
            key = str(widget.property("crtTabKey") or "")
            if key == "welcome":
                self.tabs.removeTab(index)
                self._tab_keys.pop(key, None)
                widget.deleteLater()
                continue
            if isinstance(widget, LiveCaptureWidget):
                widget.shutdown()
            self.tabs.removeTab(index)
            self._tab_keys.pop(key, None)
            widget.deleteLater()

    def _has_active_capture(self) -> bool:
        return any(
            isinstance(self.tabs.widget(index), LiveCaptureWidget)
            and self.tabs.widget(index).is_capturing
            for index in range(self.tabs.count())
        )

    def _toggle_explorer(self, visible: bool) -> None:
        self.explorer_dock.setVisible(visible)

    def _append_output(self, text: str) -> None:
        self.output.appendPlainText(text)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._has_active_capture():
            answer = QMessageBox.question(
                self,
                "Aktywna rejestracja",
                "Trwa rejestracja CAN. Zatrzymać ją i zamknąć CRT?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, LiveCaptureWidget):
                widget.shutdown()
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        event.accept()
