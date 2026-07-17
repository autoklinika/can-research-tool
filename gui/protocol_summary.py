from __future__ import annotations

from PySide6.QtCore import QAbstractItemModel
from PySide6.QtWidgets import QLabel, QTableView


_MESSAGE_COLUMN_WIDTHS = {
    0: 100,
    1: 85,
    2: 115,
    3: 120,
    4: 135,
    5: 70,
    6: 70,
    7: 245,
    8: 70,
    9: 55,
    10: 95,
    11: 95,
    12: 310,
    13: 380,
}


def attach_protocol_summary(table: QTableView, model: QAbstractItemModel) -> None:
    for column, width in _MESSAGE_COLUMN_WIDTHS.items():
        table.setColumnWidth(column, width)

    page = table.parentWidget()
    layout = page.layout() if page is not None else None
    if layout is None:
        return

    label = QLabel()
    label.setObjectName("protocolMessageSummary")
    label.setTextInteractionFlags(label.textInteractionFlags())
    label.setStyleSheet("QLabel { padding: 3px 6px; font-weight: 600; }")
    label.setToolTip(
        "Podsumowanie dotyczy wiadomości logicznych aktualnie utrzymywanych w modelu widoku."
    )
    layout.insertWidget(0, label)

    def refresh(*_args: object) -> None:
        protocol_counts: dict[str, int] = {}
        transport_counts: dict[str, int] = {}
        incomplete = 0
        message_at = getattr(model, "message_at", None)
        for row in range(model.rowCount()):
            message = message_at(row) if callable(message_at) else None
            if message is None:
                continue
            protocol = str(message.protocol).upper()
            transport = str(message.transport).upper()
            protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
            transport_counts[transport] = transport_counts.get(transport, 0) + 1
            if not message.complete:
                incomplete += 1

        parts = [
            f"Wiadomości: {model.rowCount():,}".replace(",", " "),
            f"UDS: {protocol_counts.get('UDS', 0):,}".replace(",", " "),
            f"J1939: {protocol_counts.get('J1939', 0):,}".replace(",", " "),
            f"ISO-TP: {transport_counts.get('ISOTP', 0):,}".replace(",", " "),
            (
                "J1939 TP: "
                f"{transport_counts.get('J1939-BAM', 0) + transport_counts.get('J1939-RTS-CTS', 0):,}"
            ).replace(",", " "),
        ]
        if incomplete:
            parts.append(f"Niekompletne: {incomplete:,}".replace(",", " "))
        label.setText("  |  ".join(parts))

    model.modelReset.connect(refresh)
    model.rowsInserted.connect(refresh)
    model.rowsRemoved.connect(refresh)
    model.dataChanged.connect(refresh)
    refresh()
