from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.filter_preferences import FilterCombinationMode, ProjectFilterPreferences
from app.filters import FilterMode, FilterPreset, ProjectFilterRepository
from app.logical_records import LogicalMessageRecord
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


def _message(sequence: int, can_id: int) -> LogicalMessageRecord:
    return LogicalMessageRecord(
        sequence=sequence,
        first_timestamp_ns=sequence * 1_000_000,
        last_timestamp_ns=sequence * 1_000_000,
        protocol="raw",
        transport="raw",
        name="RAW",
        arbitration_id=can_id,
        is_extended_id=True,
        pgn=None,
        source_address=None,
        destination_address=None,
        complete=True,
        frame_sequences=(sequence,),
        payload=b"\x00",
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

        assert integration.proxy.filter_set.active_names == ("00F9", "F900")
        assert integration.proxy.filter_set.combination_mode is FilterCombinationMode.OR
        assert integration.proxy.filter_set.affects_raw_visibility is True

        # Reproduce the user action during an active Capture.
        view.apply_live_filters.setChecked(True)
        assert integration._streaming_filter_view is True
        assert integration.proxy.filter_enabled is True
        assert integration.message_proxy.filter_enabled is True
        assert view.frame_table.model() is integration.proxy
        assert view.message_table.model() is integration.message_proxy

        frames = (
            _frame(0, FILTER_IDS[0]),
            _frame(1, OTHER_ID),
            _frame(2, FILTER_IDS[1]),
        )
        messages = (
            _message(0, FILTER_IDS[0]),
            _message(1, OTHER_ID),
            _message(2, FILTER_IDS[1]),
        )

        # Feed new records through the same source-model signals and Qt worker/timer
        # path used by LiveCaptureWidget._refresh_view().
        view.frame_model.append_frames(frames)
        view.message_model.append_messages(messages)

        assert _wait_until(
            lambda: (
                integration.proxy.rowCount() == 2
                and integration.message_proxy.rowCount() == 2
                and not integration._pending_frames
                and integration._incremental_running_generation is None
            )
        )

        integration.update_status(total_received=3, logical_total=3)

        assert view.frame_table.model() is integration.proxy
        assert view.message_table.model() is integration.message_proxy
        assert {
            integration.proxy.frame_at(row).arbitration_id
            for row in range(integration.proxy.rowCount())
        } == set(FILTER_IDS)
        assert {
            integration.message_proxy.message_at(row).arbitration_id
            for row in range(integration.message_proxy.rowCount())
        } == set(FILTER_IDS)
        assert "Widoczne: 2 / bufor 3" in view.visible_label.text()
        assert "Wiadomości: 3 / widoczne 2" in view.messages_label.text()

        view.close()

    app.quit()


if __name__ == "__main__":
    main()
