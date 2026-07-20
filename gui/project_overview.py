from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.filters import ProjectFilterRepository
from app.project import CrtProject, SessionRecord
from app.project_dbc import list_project_dbc


class ProjectOverviewWidget(QWidget):
    open_live_requested = Signal()
    add_area_requested = Signal()
    import_requested = Signal()
    open_session_requested = Signal(str)

    def __init__(self, project: CrtProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self._session_paths: list[str] = []
        self._visible_sessions: list[SessionRecord] = []
        self._session_detail_values: dict[str, QLabel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QFrame(self)
        header.setObjectName("overviewHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(10, 7, 10, 7)
        header_layout.setSpacing(2)

        title = QLabel(project.manifest.name, header)
        title.setObjectName("projectOverviewTitle")
        header_layout.addWidget(title)

        path = QLabel(str(project.root), header)
        path.setObjectName("secondaryText")
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header_layout.addWidget(path)

        description = QLabel(
            project.manifest.description or "Brak opisu projektu.",
            header,
        )
        description.setObjectName("secondaryText")
        description.setWordWrap(True)
        header_layout.addWidget(description)
        root.addWidget(header)

        actions = QHBoxLayout()
        actions.setSpacing(5)
        live = QPushButton("Otwórz Live Capture", self)
        live.clicked.connect(self.open_live_requested)
        actions.addWidget(live)

        import_button = QPushButton("Importuj log", self)
        import_button.clicked.connect(self.import_requested)
        actions.addWidget(import_button)

        add_area = QPushButton("Dodaj obszar badań", self)
        add_area.clicked.connect(self.add_area_requested)
        actions.addWidget(add_area)
        actions.addStretch(1)
        root.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("projectOverviewSplitter")
        splitter.setChildrenCollapsible(False)

        sessions_group = QGroupBox("Ostatnie sesje", splitter)
        sessions_layout = QVBoxLayout(sessions_group)
        sessions_layout.setContentsMargins(6, 9, 6, 6)

        self.recent_sessions = QTableWidget(sessions_group)
        self.recent_sessions.setObjectName("recentSessionsTable")
        self.recent_sessions.setColumnCount(5)
        self.recent_sessions.setHorizontalHeaderLabels(
            ["Nazwa", "Data UTC", "Źródło", "Ramki", "Czas"]
        )
        self.recent_sessions.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.recent_sessions.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.recent_sessions.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.recent_sessions.setAlternatingRowColors(True)
        self.recent_sessions.setWordWrap(False)
        self.recent_sessions.verticalHeader().setVisible(False)
        self.recent_sessions.verticalHeader().setDefaultSectionSize(23)
        header_view = self.recent_sessions.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.recent_sessions.currentCellChanged.connect(
            self._update_selected_session_details
        )
        self.recent_sessions.cellDoubleClicked.connect(self._open_session_row)
        sessions_layout.addWidget(self.recent_sessions)
        splitter.addWidget(sessions_group)

        right_splitter = QSplitter(Qt.Orientation.Vertical, splitter)
        right_splitter.setObjectName("projectOverviewDetailsSplitter")
        right_splitter.setChildrenCollapsible(False)

        config_group = QGroupBox("Konfiguracja projektu", right_splitter)
        config_group.setObjectName("projectConfigurationGroup")
        config = QFormLayout(config_group)
        config.setContentsMargins(9, 12, 9, 9)
        config.setHorizontalSpacing(16)
        config.setVerticalSpacing(5)

        sessions = project.list_sessions()
        areas = project.list_study_areas()
        dbc_records = list_project_dbc(project)
        active_dbc = sum(record.enabled for record in dbc_records)
        try:
            presets = ProjectFilterRepository(project.database_path).list_presets()
            active_filters = sum(preset.enabled for preset in presets)
        except Exception:
            presets = []
            active_filters = 0

        total_frames = sum(session.frame_count for session in sessions)
        config.addRow("Sesje CAN:", QLabel(str(len(sessions))))
        config.addRow(
            "Ramki łącznie:",
            QLabel(f"{total_frames:,}".replace(",", " ")),
        )
        config.addRow("Obszary badań:", QLabel(str(len(areas))))
        config.addRow(
            "DBC:",
            QLabel(f"{active_dbc} aktywnych / {len(dbc_records)}"),
        )
        config.addRow(
            "Filtry:",
            QLabel(f"{active_filters} aktywnych / {len(presets)}"),
        )
        config.addRow(
            "Domyślny bitrate:",
            QLabel(f"{project.manifest.default_bitrate:,} bit/s".replace(",", " ")),
        )
        config.addRow(
            "Tryb odbioru:",
            QLabel(project.manifest.default_receive_mode.upper()),
        )
        config.addRow("Utworzono:", QLabel(project.manifest.created_at_utc))
        right_splitter.addWidget(config_group)

        session_group = QGroupBox("Szczegóły sesji", right_splitter)
        session_group.setObjectName("selectedSessionDetailsGroup")
        session_form = QFormLayout(session_group)
        session_form.setContentsMargins(9, 12, 9, 9)
        session_form.setHorizontalSpacing(16)
        session_form.setVerticalSpacing(5)

        for key, caption in (
            ("name", "Nazwa:"),
            ("created", "Data UTC:"),
            ("source", "Źródło:"),
            ("status", "Status:"),
            ("frames", "Ramki:"),
            ("markers", "Markery:"),
            ("duration", "Czas:"),
            ("path", "Plik:"),
        ):
            value = QLabel("—", session_group)
            value.setObjectName(f"selectedSession{key.title()}Value")
            value.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            value.setWordWrap(key == "path")
            self._session_detail_values[key] = value
            session_form.addRow(caption, value)

        right_splitter.addWidget(session_group)
        right_splitter.setSizes([420, 420])
        splitter.addWidget(right_splitter)

        splitter.setSizes([780, 360])
        root.addWidget(splitter, 1)

        self._populate_recent_sessions(sessions)

    def _populate_recent_sessions(self, sessions: list[SessionRecord]) -> None:
        self._visible_sessions = sessions[:15]
        self.recent_sessions.setRowCount(len(self._visible_sessions))
        self._session_paths = []

        for row, session in enumerate(self._visible_sessions):
            path = str(self.project.absolute_path(session.relative_path))
            self._session_paths.append(path)
            source = self._source_label(session)
            created = session.created_at_utc.replace("T", " ")[:19]
            values = (
                session.name,
                created,
                source,
                f"{session.frame_count:,}".replace(",", " "),
                f"{session.duration_s:.3f} s",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {3, 4}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                self.recent_sessions.setItem(row, column, item)

        if self._visible_sessions:
            self.recent_sessions.selectRow(0)
            self._show_session_details(self._visible_sessions[0])
        else:
            self._clear_session_details()

    def _update_selected_session_details(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        if 0 <= current_row < len(self._visible_sessions):
            self._show_session_details(self._visible_sessions[current_row])
        else:
            self._clear_session_details()

    def _show_session_details(self, session: SessionRecord) -> None:
        values = {
            "name": session.name,
            "created": session.created_at_utc.replace("T", " ")[:19],
            "source": self._source_label(session),
            "status": session.status,
            "frames": f"{session.frame_count:,}".replace(",", " "),
            "markers": f"{session.marker_count:,}".replace(",", " "),
            "duration": f"{session.duration_s:.3f} s",
            "path": session.relative_path,
        }
        for key, value in values.items():
            self._session_detail_values[key].setText(value)

    def _clear_session_details(self) -> None:
        for label in self._session_detail_values.values():
            label.setText("—")

    @staticmethod
    def _source_label(session: SessionRecord) -> str:
        return "Import" if session.source.startswith("imported") else "Live"

    def _open_session_row(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._session_paths):
            self.open_session_requested.emit(self._session_paths[row])
