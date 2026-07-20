from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtWidgets import QTabWidget, QWidget

from app.enhanced_stored_session_controller import (
    EnhancedStoredSessionController as StoredSessionController,
)
from app.live_capture_controller import LiveCaptureController
from app.project import CrtProject
from infrastructure.desktop import reveal_path

from .async_dbc_manager import AsyncDbcManagerWidget
from .bounded_live_capture import BoundedLiveCaptureWidget
from .compact_filter_manager import CompactFilterManagerWidget as FilterManagerWidget
from .enhanced_session_filter_integration import EnhancedStoredSessionIntegration
from .final_streaming_filter_integration import (
    FinalStreamingLiveFilterIntegration as StreamingLiveFilterIntegration,
)
from .import_task import ProjectImportTask
from .project_dialog import NewProjectDialog
from .project_explorer import ProjectExplorer
from .project_navigator import ProjectNavigator
from .project_overview import ProjectOverviewWidget
from .session_management_integration import SessionManagementIntegration
from .session_view import SessionViewWidget
from .study_area_view import StudyAreaViewWidget

if TYPE_CHECKING:
    from .main_window import MainWindow


class ApplicationContainer:
    """Composition root for GUI services, controllers and view factories."""

    STORED_SESSION_PAGE_ROWS = 2_000

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
        # Temporary startup safety fallback. The Stage-1 dock shell triggers a
        # native Qt abort on the physical Windows workstation although CI's
        # offscreen GUI tests pass. Keep the stable pre-Stage-1 window active
        # until the native-shell failure is isolated.
        from .static_filter_manager_window import StaticFilterWindowMainWindow as MainWindow

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

    def create_live_capture_view(self, project: CrtProject) -> BoundedLiveCaptureWidget:
        controller = self._live_controller_factory()
        return BoundedLiveCaptureWidget(
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
            page_size=self.STORED_SESSION_PAGE_ROWS,
        )
        return SessionViewWidget(
            session_path,
            dbc_paths=dbc_paths,
            controller=controller,
            stored_integration_factory=EnhancedStoredSessionIntegration,
        )

    def create_project_overview(self, project: CrtProject) -> ProjectOverviewWidget:
        return ProjectOverviewWidget(project)

    def create_dbc_manager(self, project: CrtProject) -> AsyncDbcManagerWidget:
        return AsyncDbcManagerWidget(project)

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
