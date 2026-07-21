from __future__ import annotations

from .restorable_dock_shell import RestorableDockEngineeringShellMainWindow


class FixedMarkerMenuMainWindow(RestorableDockEngineeringShellMainWindow):
    """Restorable shell with menus built without stale QMenu references."""

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
        view_menu.addAction(self.toggle_primary_toolbar_action)
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
        tools_menu.addAction(self.session_markers_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.settings_action)
