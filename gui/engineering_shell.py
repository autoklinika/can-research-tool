from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QSizePolicy,
    QStyle,
    QTabWidget,
    QToolBar,
    QWidget,
)

from .static_filter_manager_window import StaticFilterWindowMainWindow


class EngineeringShellMainWindow(StaticFilterWindowMainWindow):
    """Classic IDE-style application shell for CRT.

    This class changes window composition, navigation and visual hierarchy only.
    Capture, Kvaser, session, decoder and filter behavior remain owned by the
    existing controllers and integrations.
    """

    WORKSPACE_STATE_VERSION = 1
    GEOMETRY_KEY = "ui/engineeringShellGeometry"
    STATE_KEY = "ui/engineeringShellState"

    def __init__(self, services) -> None:
        super().__init__(services)
        self.setObjectName("engineeringMainWindow")
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
        )
        self.setCorner(Qt.Corner.TopLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self._restore_workspace_layout()
        self._update_project_context()
        self._set_capture_status(self.capture_status.text())

    def _build_actions(self) -> None:
        super()._build_actions()

        self.toggle_explorer_action.setShortcut("Ctrl+B")
        self.toggle_explorer_action.setToolTip("Pokaż lub ukryj Explorer projektu (Ctrl+B)")

        self.overview_action = QAction("Przegląd", self)
        self.overview_action.setToolTip("Otwórz przegląd aktualnego projektu")
        self.overview_action.triggered.connect(self._open_overview)

        self.analysis_action = QAction("Analiza", self)
        self.analysis_action.setToolTip("Otwórz obszar wyszukiwania i analiz")
        self.analysis_action.triggered.connect(
            lambda: self._open_placeholder(
                "search",
                "Analiza",
                "Wyszukiwanie, porównania sesji i analiza sygnałów",
            )
        )

        self.toggle_inspector_action = QAction("Inspektor", self)
        self.toggle_inspector_action.setCheckable(True)
        self.toggle_inspector_action.setChecked(True)
        self.toggle_inspector_action.setShortcut("Ctrl+Shift+I")
        self.toggle_inspector_action.setToolTip(
            "Pokaż lub ukryj Inspektor (Ctrl+Shift+I)"
        )

        self.toggle_output_action = QAction("Panel dolny", self)
        self.toggle_output_action.setCheckable(True)
        self.toggle_output_action.setChecked(True)
        self.toggle_output_action.setShortcut("Ctrl+J")
        self.toggle_output_action.setToolTip(
            "Pokaż lub ukryj Output / Problemy / Zadania (Ctrl+J)"
        )

        self.reset_layout_action = QAction("Resetuj układ okna", self)
        self.reset_layout_action.setToolTip(
            "Przywróć domyślny układ docków i pasków narzędzi"
        )
        self.reset_layout_action.triggered.connect(self._reset_workspace_layout)

        style = self.style()
        standard = QStyle.StandardPixmap
        self.new_project_action.setIcon(style.standardIcon(standard.SP_FileIcon))
        self.open_project_action.setIcon(style.standardIcon(standard.SP_DirOpenIcon))
        self.import_action.setIcon(style.standardIcon(standard.SP_DialogOpenButton))
        self.overview_action.setIcon(style.standardIcon(standard.SP_DesktopIcon))
        self.live_action.setIcon(style.standardIcon(standard.SP_MediaPlay))
        self.analysis_action.setIcon(style.standardIcon(standard.SP_FileDialogDetailedView))
        self.decoders_action.setIcon(style.standardIcon(standard.SP_FileDialogContentsView))
        self.filters_action.setIcon(style.standardIcon(standard.SP_FileDialogListView))
        self.settings_action.setIcon(style.standardIcon(standard.SP_ComputerIcon))
        self.toggle_explorer_action.setIcon(style.standardIcon(standard.SP_DirIcon))

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.clear()

        file_menu = menu_bar.addMenu("Plik")
        file_menu.addAction(self.new_project_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addSeparator()
        file_menu.addAction(self.import_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        view_menu = menu_bar.addMenu("Widok")
        view_menu.addAction(self.toggle_explorer_action)
        view_menu.addAction(self.toggle_inspector_action)
        view_menu.addAction(self.toggle_output_action)
        view_menu.addSeparator()
        view_menu.addAction(self.reset_layout_action)

        capture_menu = menu_bar.addMenu("Capture")
        capture_menu.addAction(self.live_action)

        analysis_menu = menu_bar.addMenu("Analiza")
        analysis_menu.addAction(self.search_action)
        analysis_menu.addAction(self.compare_action)
        analysis_menu.addAction(self.signals_action)

        tools_menu = menu_bar.addMenu("Narzędzia")
        tools_menu.addAction(self.decoders_action)
        tools_menu.addAction(self.filters_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.settings_action)

    def _build_activity_bar(self) -> None:
        activity = QToolBar("Aktywność", self)
        activity.setObjectName("activityBar")
        activity.setOrientation(Qt.Orientation.Vertical)
        activity.setMovable(False)
        activity.setFloatable(False)
        activity.setIconSize(QSize(20, 20))
        activity.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        activity.setMinimumWidth(46)
        activity.setMaximumWidth(46)
        activity.addAction(self.toggle_explorer_action)
        activity.addAction(self.live_action)
        activity.addAction(self.analysis_action)
        activity.addSeparator()
        activity.addAction(self.decoders_action)
        activity.addAction(self.filters_action)
        activity.addSeparator()
        activity.addAction(self.settings_action)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, activity)
        self.activity_bar = activity

        primary = QToolBar("Narzędzia główne", self)
        primary.setObjectName("primaryToolBar")
        primary.setMovable(True)
        primary.setFloatable(False)
        primary.setIconSize(QSize(16, 16))
        primary.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        primary.addAction(self.new_project_action)
        primary.addAction(self.open_project_action)
        primary.addAction(self.import_action)
        primary.addSeparator()
        primary.addAction(self.overview_action)
        primary.addAction(self.live_action)
        primary.addSeparator()
        primary.addAction(self.decoders_action)
        primary.addAction(self.filters_action)

        spacer = QWidget(primary)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        primary.addWidget(spacer)

        self.project_context_label = QLabel("Brak projektu", primary)
        self.project_context_label.setObjectName("toolbarProjectContext")
        primary.addWidget(self.project_context_label)

        self.capture_indicator = QLabel("STOPPED", primary)
        self.capture_indicator.setObjectName("captureIndicator")
        self.capture_indicator.setProperty("state", "stopped")
        primary.addWidget(self.capture_indicator)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, primary)
        self.primary_toolbar = primary

    def _build_docks(self) -> None:
        super()._build_docks()

        dock_features = (
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.explorer_dock.setFeatures(dock_features)
        self.explorer_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.explorer_dock.setMinimumWidth(230)

        self.inspector_dock.setFeatures(dock_features)
        self.inspector_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.inspector_dock.setMinimumWidth(260)

        self.output_dock.setWindowTitle("Output")
        self.output_dock.setFeatures(dock_features)
        self.output_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.output_dock.setMinimumHeight(110)

        output_tabs = self.output_dock.widget()
        if isinstance(output_tabs, QTabWidget):
            output_tabs.setObjectName("outputTabs")
            can_log = QPlainTextEdit(output_tabs)
            can_log.setReadOnly(True)
            can_log.setMaximumBlockCount(5000)
            can_log.setPlaceholderText(
                "Log transportu i komunikacji CAN pojawi się tutaj, gdy moduł go udostępni."
            )
            output_tabs.addTab(can_log, "Log CAN")
            self.can_log = can_log
            self.output_tabs = output_tabs

        self.toggle_inspector_action.triggered.connect(self.inspector_dock.setVisible)
        self.toggle_output_action.triggered.connect(self.output_dock.setVisible)
        self.inspector_dock.visibilityChanged.connect(
            self.toggle_inspector_action.setChecked
        )
        self.output_dock.visibilityChanged.connect(self.toggle_output_action.setChecked)

        if hasattr(self.explorer, "open_filters"):
            self.explorer.open_filters.connect(self._open_filters)

        self.resizeDocks(
            [self.explorer_dock, self.inspector_dock],
            [280, 320],
            Qt.Orientation.Horizontal,
        )
        self.resizeDocks(
            [self.output_dock],
            [180],
            Qt.Orientation.Vertical,
        )

    def _build_central_tabs(self) -> None:
        super()._build_central_tabs()
        self.tabs.setObjectName("workspaceTabs")
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.setUsesScrollButtons(True)

        bar = self.tabs.tabBar()
        bar.setExpanding(False)
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._show_tab_context_menu)

    def _build_status_bar(self) -> None:
        super()._build_status_bar()
        status = self.statusBar()
        status.setSizeGripEnabled(True)

        self.project_status.setObjectName("projectStatus")
        self.capture_status.setObjectName("captureStatus")
        self.capture_status.setMinimumWidth(82)

        status.removeWidget(self.capture_status)
        self.transport_status = QLabel("CAN: —")
        self.transport_status.setObjectName("transportStatus")
        self.mode_status = QLabel("TRYB: —")
        self.mode_status.setObjectName("modeStatus")
        status.addPermanentWidget(self.transport_status)
        status.addPermanentWidget(self.mode_status)
        status.addPermanentWidget(self.capture_status)

    def _set_project(self, project) -> None:
        super()._set_project(project)
        if self.project is not None and Path(self.project.root) == Path(project.root):
            self._update_project_context()

    def _open_overview(self) -> None:
        super()._open_overview()
        widget = self.navigator.widget("project-overview")
        if widget is None or bool(widget.property("engineeringShellBound")):
            return
        signal = getattr(widget, "open_session_requested", None)
        if signal is not None:
            signal.connect(self._open_session)
        widget.setProperty("engineeringShellBound", True)

    def _open_live_capture(self) -> None:
        super()._open_live_capture()
        widget = self.navigator.widget("live-capture")
        if widget is None or bool(widget.property("engineeringShellBound")):
            return
        widget.status_text.connect(self._set_capture_status)
        widget.project_changed.connect(self._update_project_context)
        widget.setProperty("engineeringShellBound", True)

    def _show_tab_context_menu(self, point: QPoint) -> None:
        bar = self.tabs.tabBar()
        index = bar.tabAt(point)
        if index < 0:
            return

        menu = QMenu(self)
        close_current = menu.addAction("Zamknij")
        close_others = menu.addAction("Zamknij inne")
        close_all = menu.addAction("Zamknij wszystkie")
        selected = menu.exec(bar.mapToGlobal(point))

        if selected is close_current:
            if self._tab_is_closable(index):
                self._close_tab(index)
        elif selected is close_others:
            self._close_tabs_except(index)
        elif selected is close_all:
            self._close_all_closable_tabs()

    def _tab_is_closable(self, index: int) -> bool:
        widget = self.tabs.widget(index)
        if widget is None:
            return False
        return str(widget.property("crtTabKey") or "") != "welcome"

    def _close_tabs_except(self, keep_index: int) -> None:
        keep_widget = self.tabs.widget(keep_index)
        for index in range(self.tabs.count() - 1, -1, -1):
            widget = self.tabs.widget(index)
            if widget is keep_widget or not self._tab_is_closable(index):
                continue
            self._close_tab(index)

    def _close_all_closable_tabs(self) -> None:
        for index in range(self.tabs.count() - 1, -1, -1):
            if self._tab_is_closable(index):
                self._close_tab(index)

    def _set_capture_status(self, text: str) -> None:
        normalized = (text or "STOPPED").strip()
        upper = normalized.upper()
        if "ERROR" in upper or "BŁĄD" in upper:
            state = "error"
        elif "CONNECT" in upper or "ŁĄCZ" in upper:
            state = "connecting"
        elif (
            "CAPTUR" in upper
            or "RECORD" in upper
            or "RUNNING" in upper
            or "AKTYW" in upper
        ):
            state = "running"
        else:
            state = "stopped"

        self.capture_status.setText(normalized)
        self.capture_indicator.setText(normalized)
        self.capture_indicator.setProperty("state", state)
        style = self.capture_indicator.style()
        style.unpolish(self.capture_indicator)
        style.polish(self.capture_indicator)

    def _update_project_context(self) -> None:
        if self.project is None:
            self.project_context_label.setText("Brak projektu")
            self.transport_status.setText("CAN: —")
            self.mode_status.setText("TRYB: —")
            return

        bitrate = int(self.project.manifest.default_bitrate)
        mode = self.project.manifest.default_receive_mode.upper().replace("_", " ")
        bitrate_text = f"{bitrate // 1000} kbit/s"
        self.project_context_label.setText(
            f"{self.project.manifest.name}  |  {bitrate_text}  |  {mode}"
        )
        self.transport_status.setText(f"CAN: {bitrate_text}")
        self.mode_status.setText(f"TRYB: {mode}")

    def _restore_workspace_layout(self) -> None:
        geometry = self.settings.value(self.GEOMETRY_KEY)
        state = self.settings.value(self.STATE_KEY)
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            restored = self.restoreState(state, self.WORKSPACE_STATE_VERSION)
            if restored:
                return
        self._apply_default_layout()

    def _apply_default_layout(self) -> None:
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.explorer_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_dock)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.output_dock)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.activity_bar)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.primary_toolbar)

        self.output_dock.show()
        if self.project is None:
            self.explorer_dock.hide()
            self.inspector_dock.hide()
        else:
            self.explorer_dock.show()
            self.inspector_dock.show()

        self.resizeDocks(
            [self.explorer_dock, self.inspector_dock],
            [280, 320],
            Qt.Orientation.Horizontal,
        )
        self.resizeDocks([self.output_dock], [180], Qt.Orientation.Vertical)

    def _reset_workspace_layout(self) -> None:
        self.settings.remove(self.GEOMETRY_KEY)
        self.settings.remove(self.STATE_KEY)
        self._apply_default_layout()
        self._append_output("Przywrócono domyślny układ okna.")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        super().closeEvent(event)
        if not event.isAccepted():
            return
        self.settings.setValue(self.GEOMETRY_KEY, self.saveGeometry())
        self.settings.setValue(
            self.STATE_KEY,
            self.saveState(self.WORKSPACE_STATE_VERSION),
        )
