from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGroupBox, QPlainTextEdit, QTableWidget

from app.logical_cache import ensure_logical_cache
from app.logical_records import LogicalMessageRecord
from app.models import CanFrame, CaptureSession
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer
from gui.protocol_message_details import ProtocolMessageDetailsDialog


def _dbc_record() -> LogicalMessageRecord:
    return LogicalMessageRecord(
        sequence=7,
        first_timestamp_ns=10_000_000,
        last_timestamp_ns=10_000_000,
        protocol="dbc",
        transport="raw",
        name="DBC EngineData",
        arbitration_id=0x18FF50A5,
        is_extended_id=True,
        pgn=0xFF50,
        source_address=0xA5,
        destination_address=None,
        complete=True,
        frame_sequences=(7,),
        payload=bytes.fromhex("7D 57 00 00 00 00 00 00"),
        confidence=1.0,
        fields={
            "dbc_file": "engine.dbc",
            "dbc_message": "EngineData",
            "sender_name": "Engine ECU",
            "dbc_match_mode": "j1939-address-aware",
            "signals": {"RPM": 798.0, "TempCoolant": 87},
            "signal_units": {"RPM": "rpm", "TempCoolant": "°C"},
        },
    )


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        session_path = Path(directory) / "details.crt.jsonl"
        with SessionStreamWriter(
            CaptureSession(name="Message details", source="test"),
            session_path,
        ) as writer:
            writer.append(
                CanFrame(
                    sequence=0,
                    timestamp_ns=0,
                    arbitration_id=0x18DAF900,
                    data=bytes.fromhex("02 10 03"),
                    is_extended_id=True,
                )
            )

        cache = ensure_logical_cache(session_path)
        widget = ApplicationContainer().create_session_view(session_path)
        widget._display_model.set_cache(cache.path)
        widget.message_table.show()
        widget.show()
        app.processEvents()

        index = widget._display_model.index(0, 0)
        assert index.isValid()
        widget.message_table.doubleClicked.emit(index)
        app.processEvents()

        dialogs = widget.findChildren(ProtocolMessageDetailsDialog)
        assert len(dialogs) == 1
        uds_dialog = dialogs[0]
        assert uds_dialog.protocol_key == "uds"
        assert uds_dialog.findChild(QGroupBox, "udsDetailsGroup") is not None
        payload = uds_dialog.findChild(QPlainTextEdit, "rawPayloadView")
        assert payload is not None
        assert payload.toPlainText() == "10 03"

        dbc_dialog = ProtocolMessageDetailsDialog(_dbc_record(), widget)
        dbc_dialog.show()
        app.processEvents()
        assert dbc_dialog.findChild(QGroupBox, "dbcDetailsGroup") is not None
        signal_table = dbc_dialog.findChild(QTableWidget, "dbcSignalTable")
        assert signal_table is not None
        assert signal_table.rowCount() == 2
        values = {
            signal_table.item(row, 0).text(): (
                signal_table.item(row, 1).text(),
                signal_table.item(row, 2).text(),
            )
            for row in range(signal_table.rowCount())
        }
        assert values["RPM"] == ("798", "rpm")
        assert values["TempCoolant"] == ("87", "°C")

        dbc_dialog.close()
        uds_dialog.close()
        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
