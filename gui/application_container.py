from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtWidgets import QTabWidget, QWidget

from app.enhanced_stored_session_controller import (
    EnhancedStoredSessionController as StoredSessionController,
)
from app.live_capture_controller import LiveCaptureController
from app.live_performance import maybe_instrument_live_controller
from app.project import CrtProject
from infrastructure.desktop import reveal_path

from .dbc_manager import DbcManagerWidget
from .enhanced_filter_manager import EnhancedFilterManagerWidget as FilterManagerWidget
from .enhanced_session_filter_integration import EnhancedStoredSessionIntegration
from .final_streaming_filter_integration import (
    FinalStreamingLiveFilterIntegration as StreamingLiveFilterIntegration,
)
from .import_task import ProjectImportTask
from .live_capture import LiveCaptureWidget
from .project_dialog import NewProjectDialog
from .project_explorer import ProjectExplorer
from .project_navigator import ProjectNavigator
from .project_overview import ProjectOverviewWidget
from .session_management_integration import SessionManagementIntegration
from .session_view import SessionViewWidget
from .stage_h_live_capture import live_capture_widget_type
from .study_area_view import StudyAreaViewWidget

if TYPE_CHECKING:
    from .main_window import MainWindow


class ApplicationContainer:
    """Composition root for GUI services, controllers and view factories."""

    def __init__(
        self,
        *,
        live_controller_factory: Callable[..., LiveCaptureController] = (
            LiveCaptureController
        ),
        stored_controller_factory: Callable[..., StoredSessionController] = (
            StoredSessionController
        ),
        reveal_path_fn: Callable[[Path], bool] = reveal_path,
    ) -> None:
        self._live_controller_factory = live_controller_factory
        self._stored_controller_factory = stored_controller_factory
        self._reveal_path_fn = reveal_path_fn

    def create_main_window(self) -> MainWindow:
        from .filter_manager_window import WindowedFilterMainWindow as MainWindow

        return MainWindow(self)

    def create_project_explorer(self) -> ProjectExplorer:
        return ProjectExplorer()

    def create_project_navigator(self, tabs: QTabWidget) -> ProjectNavigator:
        return ProjectNavigator(tabs, session_widget_factory=self.create_session_view)

    def create_session_management(
        self,
        window: MainWindow,
    ) -> SessionManagementIntegration:
        return SessionManagementIntegration(
            window,
            reveal_path_fn=self._reveal_path_fn,
        )

    def create_project_dialog(self, parent: QWidget) -> NewProjectDialog:
        return NewProjectDialog(parent)

    def create_live_capture_view(self, project: CrtProject) -> LiveCaptureWidget:
        controller = self._live_controller_factory()
        controller = maybe_instrument_live_controller(
            controller,
            report_dir=project.root / "reports",
        )
        widget_type = live_capture_widget_type()
        return widget_type(
            project,
            controller=controller,
            filter_integration_factory=StreamingLiveFilterIntegration,
        )

    def create_session_view(
        self,
        path: str | Path,
        *,
        dbc_paths: tuple[Path, ...] = (),
    ) -> SessionViewWidget:
        session_path = Path(path)
        controller = self._stored_controller_factory(
            session_path,
            page_size=SessionViewWidget.MAX_ROWS,
        )
        return SessionViewWidget(
            session_path,
            dbc_paths=dbc_paths,
            controller=controller,
            stored_integration_factory=EnhancedStoredSessionIntegration,
        )

    def create_project_overview(self, project: CrtProject) -> ProjectOverviewWidget:
        return ProjectOverviewWidget(project)

    def create_dbc_manager(self, project: CrtProject) -> DbcManagerWidget:
        return DbcManagerWidget(project)

    def create_filter_manager(self, project: CrtProject) -> FilterManagerWidget:
        return FilterManagerWidget(project)

    def create_study_area_view(
        self,
        project: CrtProject,
        area_id: str,
    ) -> StudyAreaViewWidget:
        return StudyAreaViewWidget(project, area_id)

    def create_import_task(
        self,
        project: CrtProject,
        source_path: str | Path,
    ) -> ProjectImportTask:
        return ProjectImportTask(project, source_path)
