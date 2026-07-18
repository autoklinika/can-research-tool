from __future__ import annotations

from tempfile import TemporaryDirectory
from time import monotonic

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from app.filters import FilterMode, FilterPreset, ProjectFilterRepository
from app.logical_records import LogicalMessageRecord
from app.models import CanFrame
from app.project import CrtProject
from gui.filter_manager import FilterManagerWidget
from gui.live_capture import LiveCaptureWidget


def _message(
    sequence: int,
    *,
    protocol: str,
    did: int | None = None,
) -> LogicalMessageRecord:
    fields: dict[str, object] = {}
    if did is not None:
        fields.update(
            {
                "service_id": 0x62,
                "base_service_id": 0x22,
                "direction": "positive-response",
                "response_type": "positive-response",
                "service_name": "ReadDataByIdentifier",
                "did": did,
                "addressing": "normal-11bit",
            }
        )
    return LogicalMessageRecord(
        sequence=sequence,
        first_timestamp_ns=sequence * 1_000_000,
        last_timestamp_ns=sequence * 1_000_000 + 100_000,
        protocol=protocol,
        transport="isotp" if protocol == "uds" else "raw",
        name="UDS F190" if protocol == "uds" else "J1939 message",
        arbitration_id=0x7E8 if protocol == "uds" else 0x18FEEE30,
        is_extended_id=protocol != "uds",
        pgn=None if protocol == "uds" else 0xFEEE,
        source_address=None if protocol == "uds" else 0x30,
        destination_address=None,
        complete=True,
        frame_sequences=(sequence,),
        payload=bytes.fromhex("62 F1 90") if protocol == "uds" else b"\x00" * 8,
        fields=fields,
    )


def main() -> None:
    app = QApplication.instance() or QApplication([])

    with TemporaryDirectory() as temporary:
        project = CrtProject.create(f"{temporary}/project", name="Protocol GUI filters")
        preset = FilterPreset.create("Only UDS F190")
        preset.enabled = True
        preset.mode = FilterMode.INCLUDE
        preset.scope = ["live"]
        preset.root = {
            "type": "group",
            "operator": "and",
            "children": [
                {
                    "type": "condition",
                    "field": "protocol",
                    "operator": "eq",
                    "values": ["uds"],
                },
                {
                    "type": "condition",
                    "field": "did",
                    "operator": "eq",
                    "values": ["0xF190"],
                },
            ],
        }
        ProjectFilterRepository(project.database_path).save_presets([preset])

        manager = FilterManagerWidget(project)
        for field in (
            "pgn",
            "j1939_transport",
            "addressing",
            "isotp_framing",
            "sid",
            "did",
            "suppress_positive_response",
        ):
            assert manager.condition_field.findData(field) >= 0
        manager.close()

        widget = LiveCaptureWidget(project)
        widget.frame_model.append_frames(
            [
                CanFrame(
                    sequence=1,
                    timestamp_ns=1_000_000,
                    arbitration_id=0x123,
                    data=b"\x00",
                ),
                CanFrame(
                    sequence=2,
                    timestamp_ns=2_000_000,
                    arbitration_id=0x456,
                    data=b"\x00",
                ),
            ]
        )
        widget.message_model.append_messages(
            [
                _message(1, protocol="uds", did=0xF190),
                _message(2, protocol="j1939"),
            ]
        )
        widget.live_filter_proxy.reload_project_filters()
        widget.apply_live_filters.setChecked(True)
        assert widget.frame_table.model() is widget.frame_model
        assert widget.message_table.model() is widget.message_model

        deadline = monotonic() + 10.0
        while monotonic() < deadline:
            app.processEvents()
            QThreadPool.globalInstance().waitForDone(20)
            if widget.live_message_filter_proxy.filter_ready:
                break

        app.processEvents()
        assert widget.live_filter_proxy.filter_enabled is False
        assert widget.frame_table.model() is widget.frame_model
        assert widget.message_table.model() is widget.live_message_filter_proxy
        assert widget.live_filter_proxy.rowCount() == 2
        assert widget.live_message_filter_proxy.rowCount() == 1

        widget.message_model.append_messages(
            [
                _message(3, protocol="j1939"),
                _message(4, protocol="uds", did=0xF190),
            ]
        )
        app.processEvents()
        assert widget.live_message_filter_proxy.rowCount() == 2

        widget.apply_live_filters.setChecked(False)
        app.processEvents()
        assert widget.live_message_filter_proxy.rowCount() == 4
        widget.close()

    app.processEvents()


if __name__ == "__main__":
    main()
