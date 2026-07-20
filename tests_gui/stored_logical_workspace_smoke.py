from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from app.models import CanFrame, CaptureSession
from app.session_stream import SessionStreamWriter
from gui.application_container import ApplicationContainer


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        session_path = Path(directory) / "layout.crt.jsonl"
        with SessionStreamWriter(
            CaptureSession(name="Logical layout", source="test"),
            session_path,
        ) as writer:
            writer.append(
                CanFrame(
                    sequence=0,
                    timestamp_ns=0,
                    arbitration_id=0x18DAF900,
                    data=b"\x02\x10\x03",
                    is_extended_id=True,
                )
            )

        widget = ApplicationContainer().create_session_view(session_path)
        assert widget.header.isHidden()
        assert widget.protocol_filter.objectName() == "logicalProtocolFilter"
        assert widget.sender_filter.objectName() == "logicalSenderFilter"
        assert widget.identity_filter.objectName() == "logicalIdentityFilter"
        assert widget.time_from_filter.objectName() == "logicalTimeFromFilter"
        assert widget.time_to_filter.objectName() == "logicalTimeToFilter"
        assert widget.data_offset_filter.objectName() == "logicalDataOffsetFilter"
        assert widget.data_value_filter.objectName() == "logicalDataValueFilter"
        assert widget.only_errors_filter.text() == "Tylko błędy"
        assert widget.hide_periodic_filter.text() == "Ukryj okresowe"
        assert widget.apply_message_filters_button.text() == "Zastosuj"
        assert widget.clear_message_filters_button.text() == "Wyczyść"
        assert widget.external_message_button.text() == "Załaduj ponownie"
        assert widget.message_table.objectName() == "storedLogicalMessageTable"
        assert widget.message_table.verticalHeader().isHidden()

        model = widget.message_table.model()
        assert model is not None
        assert model.columnCount() == 8
        expected = (
            "Czas [s]",
            "ID",
            "Nazwa",
            "Nadawca",
            "Protokół",
            "DLC",
            "Dane",
            "Wartości (zdekodowane)",
        )
        actual = tuple(
            model.headerData(column, Qt.Orientation.Horizontal)
            for column in range(model.columnCount())
        )
        assert actual == expected

        titles = {
            label.text()
            for label in widget.findChildren(QLabel, "logicalSectionTitle")
        }
        assert titles == {"FILTRY", "ŁADOWANIE WIADOMOŚCI LOGICZNYCH"}

        widget.shutdown()
        widget.close()
        widget.deleteLater()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
