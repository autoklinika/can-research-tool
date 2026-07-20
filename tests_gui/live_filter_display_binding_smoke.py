from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication

from app.combined_filters import CombinedActiveFilterSet
from app.filter_preferences import FilterCombinationMode
from app.filters import FilterMode, FilterPreset
from app.logical_records import LogicalMessageRecord
from app.models import CanFrame
from app.project import CrtProject
from gui.application_container import ApplicationContainer
from gui.logical_filter_integration import (
    LogicalFilterScanResult,
    logical_message_key,
)


FILTER_IDS = (0x18DAF900, 0x18DA00F9)
OTHER_ID = 0x18FEEE30


class FakeLiveController:
    def list_adapters(self):
        return []

    @property
    def is_active(self) -> bool:
        return False


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


def main() -> None:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(Path(temporary) / "project", name="Filter Binding")
        container = ApplicationContainer(live_controller_factory=FakeLiveController)
        view = container.create_live_capture_view(project)
        view.timer.stop()
        integration = view._live_filter_integration

        filter_set = CombinedActiveFilterSet(
            [_preset("F900", FILTER_IDS[0]), _preset("00F9", FILTER_IDS[1])],
            scope="live",
            combination_mode=FilterCombinationMode.OR,
        )
        integration.proxy.filter_set = filter_set
        integration.proxy._signature = filter_set.signature
        integration.message_proxy.set_filter_set(filter_set)

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
        view.frame_model.append_frames(frames)
        view.message_model.append_messages(messages)

        integration.proxy.set_filter_enabled(True)
        integration.proxy.apply_background_result((frames[0], frames[2]), 2)

        integration.message_proxy.set_filter_enabled(True)
        accepted_keys = frozenset(
            logical_message_key(message)
            for message in (messages[0], messages[2])
        )
        integration.message_proxy.apply_background_result(
            LogicalFilterScanResult(
                accepted_keys=accepted_keys,
                evaluated_keys=frozenset(logical_message_key(message) for message in messages),
            )
        )

        # Reproduce the reported inconsistency: counters use filtered proxies while
        # QTableViews have drifted back to their unfiltered source models.
        view.frame_table.setModel(view.frame_model)
        view.message_table.setModel(view.message_model)
        assert view.frame_table.model() is view.frame_model
        assert view.message_table.model() is view.message_model

        integration.update_status(total_received=3, logical_total=3)

        assert view.frame_table.model() is integration.proxy
        assert view.message_table.model() is integration.message_proxy
        assert integration.proxy.rowCount() == 2
        assert integration.message_proxy.rowCount() == 2
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
