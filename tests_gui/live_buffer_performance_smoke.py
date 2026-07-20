from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app.logical_records import LogicalMessageRecord
from app.models import CanFrame
from gui.frame_model import FrameTableModel
from gui.logical_filter_integration import LogicalMessageFilterProxy
from gui.logical_message_model import LogicalMessageTableModel


def _frame(sequence: int) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=sequence * 1_000,
        arbitration_id=0x100 + (sequence % 4),
        data=b"\x00",
    )


def _message(sequence: int, *, protocol: str, complete: bool = True) -> LogicalMessageRecord:
    return LogicalMessageRecord(
        sequence=sequence,
        first_timestamp_ns=sequence * 1_000_000,
        last_timestamp_ns=sequence * 1_000_000,
        protocol=protocol,
        transport="isotp" if protocol == "uds" else "raw",
        name=protocol,
        arbitration_id=0x7E8 if protocol == "uds" else 0x18FEEE30,
        is_extended_id=protocol != "uds",
        pgn=None if protocol == "uds" else 0xFEEE,
        source_address=None if protocol == "uds" else 0x30,
        destination_address=None,
        complete=complete,
        frame_sequences=(sequence,),
        payload=b"\x00",
    )


def main() -> None:
    app = QApplication.instance() or QApplication([])

    frame_model = FrameTableModel(capacity=100)
    frame_model.append_frames(_frame(index) for index in range(100))
    frame_model.append_frames([_frame(100)])
    # Capacity rollover removes a 10% chunk instead of shifting the full list
    # on every subsequent GUI refresh.
    assert frame_model.rowCount() == 91
    assert frame_model.frame_at(0).sequence == 10
    assert frame_model.frame_at(90).sequence == 100

    message_model = LogicalMessageTableModel(capacity=100)
    message_model.append_messages(
        _message(index, protocol="uds" if index % 2 == 0 else "j1939")
        for index in range(100)
    )
    message_model.append_messages([_message(100, protocol="uds", complete=False)])
    assert message_model.rowCount() == 91
    protocols, transports, incomplete = message_model.summary_counts()
    assert protocols == {"UDS": 46, "J1939": 45}
    assert transports == {"ISOTP": 46, "RAW": 45}
    assert incomplete == 1

    proxy = LogicalMessageFilterProxy()
    proxy.setSourceModel(message_model)
    assert proxy.summary_counts() == message_model.summary_counts()
    assert proxy.prune_source_cache_if_needed(1) is False

    app.processEvents()
    proxy.deleteLater()
    frame_model.deleteLater()
    message_model.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
