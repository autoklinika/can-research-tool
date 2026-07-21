from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.filter_preferences import FilterCombinationMode, ProjectFilterPreferences
from app.filters import FilterMode, FilterPreset, ProjectFilterRepository
from app.models import CanFrame
from app.project import CrtProject
from gui.application_container import ApplicationContainer


FILTER_IDS = (0x18DAF900, 0x18DA00F9)
OTHER_ID = 0x18FEEE30


class FakeLiveController:
    def list_adapters(self):
        return []

    @property
    def is_active(self) -> bool:
        # Exercise the real StreamingLiveFilterIntegration path used while Capture runs.
        return True


def _preset(name: str, can_id: int) -> FilterPreset:
    preset = FilterPreset.create(name)
    preset.mode = FilterMode.INCLUDE
    preset.scope = ["live"]
    preset.root = {
        "type": "group",
        "operator": "or",
        "children": [
            {
                "type": "condition",
                "field": "can_id",
                "operator": "eq",
                "values": [can_id],
            }
        ],
    }
    return preset


def _frame(sequence: int, can_id: int) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=sequence * 1_000_000,
        arbitration_id=can_id,
        data=b"\x00",
        is_extended_id=True,
    )


def _wait_until(predicate, *, timeout_ms: int = 2_000) -> bool:
    elapsed = 0
    while elapsed < timeout_ms:
        QApplication.processEvents()
        if predicate():
            return True
        QTest.qWait(20)
        elapsed += 20
    QApplication.processEvents()
    return bool(predicate())


def main() -> None:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(Path(temporary) / "project", name="Filter Binding")
        ProjectFilterRepository(project.database_path).save_presets(
            [_preset("F900", FILTER_IDS[0]), _preset("00F9", FILTER_IDS[1])]
        )
        ProjectFilterPreferences(project.database_path).set_combination_mode(
            FilterCombinationMode.OR
        )

        container = ApplicationContainer(live_controller_factory=FakeLiveController)
        view = container.create_live_capture_view(project)
        view.timer.stop()
        integration = view._live_filter_integration

        assert set(integration.proxy.filter_set.active_names) == {"F900", "00F9"}
        assert integration.proxy.filter_set.combination_mode is FilterCombinationMode.OR
        assert integration.proxy.filter_set.affects_raw_visibility is True

        # Reproduce applying filters while Capture runs. Live remains raw-only;
        # logical analysis is deliberately deferred until STOP.
        view.apply_live_filters.setChecked(True)
        assert integration._streaming_filter_view is True
        assert integration.proxy.filter_enabled is True
        assert view.frame_table.model() is integration.proxy
        assert view.message_table.isHidden()
        assert view.message_model.rowCount() == 0

        frames = (
            _frame(0, FILTER_IDS[0]),
            _frame(1, OTHER_ID),
            _frame(2, FILTER_IDS[1]),
        )

        # Feed new raw frames through the same source-model signal and worker/timer
        # path used by the active Live view.
        view.frame_model.append_frames(frames)

        completed = _wait_until(
            lambda: (
                integration.proxy.rowCount() == 2
                and not integration._pending_frames
                and integration._incremental_running_generation is None
            )
        )
        assert completed, (
            "active Live raw filtering did not settle: "
            f"frame_rows={integration.proxy.rowCount()} "
            f"pending={len(integration._pending_frames)} "
            f"running_generation={integration._incremental_running_generation} "
            f"frame_ready={integration.proxy.filter_ready} "
            f"frame_scanning={integration.proxy.filter_scanning} "
            f"frame_model={type(view.frame_table.model()).__name__}"
        )

        integration.update_status(total_received=3, logical_total=0)

        assert view.frame_table.model() is integration.proxy
        assert {
            integration.proxy.frame_at(row).arbitration_id
            for row in range(integration.proxy.rowCount())
        } == set(FILTER_IDS)
        assert view.message_model.rowCount() == 0
        assert "Widoczne: 2 / bufor 3" in view.visible_label.text()

        view.close()

    app.quit()


if __name__ == "__main__":
    main()
