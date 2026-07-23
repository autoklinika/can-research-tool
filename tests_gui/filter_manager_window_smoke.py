from __future__ import annotations

import gc
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication

from app.filter_preferences import FilterCombinationMode, ProjectFilterPreferences
from app.filters import FilterMode, FilterPreset, ProjectFilterRepository
from app.project import CrtProject
from gui.application_container import ApplicationContainer
from gui.filter_manager_window import FilterManagerWindow, WindowedFilterMainWindow


def _preset(name: str, shortcut: str, *, enabled: bool) -> FilterPreset:
    preset = FilterPreset.create(name)
    preset.enabled = enabled
    preset.mode = FilterMode.INCLUDE
    preset.shortcut = shortcut
    preset.scope = ["live", "stored_session"]
    preset.root = {
        "type": "condition",
        "field": "can_id",
        "operator": "eq",
        "values": ["0x100"],
    }
    return preset


def _drain_deferred_deletes(app: QApplication) -> None:
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("AutoklinikaTests")
    app.setApplicationName("CRTFilterWindowSmoke")
    QSettings().clear()

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Filter window")
        inactive = _preset("CAN 0x100", "F8", enabled=False)
        active = _preset("Second include", "F9", enabled=True)
        repository = ProjectFilterRepository(project.database_path)
        repository.save_presets([inactive, active])

        window = ApplicationContainer().create_main_window()
        assert isinstance(window, WindowedFilterMainWindow)
        window._set_project(project)

        assert window.filters_action.shortcut().toString() == "Ctrl+D"
        assert window.activity_bar.isHidden()
        primary_actions = window.primary_toolbar.actions()
        assert primary_actions.index(window.decoders_action) < primary_actions.index(
            window.filters_action
        )
        registered = {shortcut.key().toString() for shortcut in window._preset_shortcuts}
        assert registered == {"F8", "F9"}

        tab_count = window.tabs.count()
        window._open_filters()
        app.processEvents()

        filter_window = window._filter_window
        assert isinstance(filter_window, FilterManagerWindow)
        assert filter_window.isWindow()
        assert filter_window.isVisible()
        assert filter_window.full_screen_action.shortcut().toString() == "F11"
        filter_window.full_screen_action.trigger()
        app.processEvents()
        assert filter_window.isFullScreen()
        filter_window.full_screen_action.trigger()
        app.processEvents()
        assert not filter_window.isFullScreen()
        assert window.tabs.count() == tab_count
        assert "global-filters" not in window.navigator.widgets
        assert window.tabs.indexOf(filter_window.manager) == -1

        manager = filter_window.manager
        assert manager.combination_mode is FilterCombinationMode.AND
        manager.combination_combo.setCurrentIndex(
            manager.combination_combo.findData(FilterCombinationMode.OR.value)
        )
        assert manager.has_pending_changes
        assert (
            ProjectFilterPreferences(project.database_path).combination_mode()
            is FilterCombinationMode.AND
        )

        # A shortcut must not persist or bypass the editor's dirty working copy.
        window._toggle_filter_preset(inactive.id)
        saved = {preset.id: preset for preset in repository.list_presets()}
        assert saved[inactive.id].enabled is False

        manager.apply_button.click()
        app.processEvents()
        assert not manager.has_pending_changes
        assert (
            ProjectFilterPreferences(project.database_path).combination_mode()
            is FilterCombinationMode.OR
        )

        # An inactive preset keeps its shortcut registered and can be enabled globally.
        window._toggle_filter_preset(inactive.id)
        saved = {preset.id: preset for preset in repository.list_presets()}
        assert saved[inactive.id].enabled is True

        live = window.services.create_live_capture_view(project)
        live._live_filter_integration._reload_and_update()
        assert "CAN 0x100" in live.active_live_filter_label.text()
        assert "Include: OR" in live.active_live_filter_label.text()
        live.close()
        live.deleteLater()

        # Application shortcuts are reserved and block filter preset saves.
        manager.reload_from_repository()
        manager.presets[0].shortcut = "Ctrl+D"
        assert manager._save(silent=True) is False
        assert manager._shortcut_check().messages
        manager.presets[0].shortcut = "F8"
        assert manager._save(silent=True) is True

        # Reopening from the primary action/shortcut activates the same top-level window.
        window.filters_action.trigger()
        app.processEvents()
        assert window._filter_window is filter_window

        filter_window.close()
        app.processEvents()
        assert not filter_window.isVisible()
        window.filters_action.trigger()
        app.processEvents()
        assert window._filter_window is filter_window
        assert filter_window.isVisible()

        window.close()
        window.deleteLater()
        _drain_deferred_deletes(app)

        del manager
        del filter_window
        del live
        del window
        del repository
        del project
        _drain_deferred_deletes(app)

    QSettings().clear()


if __name__ == "__main__":
    main()
