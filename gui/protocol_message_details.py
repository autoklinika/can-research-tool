from __future__ import annotations

import json
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.logical_records import LogicalMessageRecord

from .stored_logical_message_panel import (
    format_logical_time,
    format_message_id,
    protocol_label,
    sender_text,
)


class ProtocolMessageDetailsDialog(QDialog):
    """Modeless protocol-aware details window for one logical CAN message."""

    def __init__(
        self,
        message: LogicalMessageRecord,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.message = message
        self.protocol_key = str(message.protocol or "unknown").strip().lower()
        self.setObjectName("protocolMessageDetailsDialog")
        self.setProperty("protocol", self.protocol_key)
        self.setModal(False)
        self.setWindowTitle(
            f"CRT — {protocol_label(self.protocol_key)} — {message.name or format_message_id(message)}"
        )
        self.resize(980, 720)
        self.setMinimumSize(720, 480)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.addWidget(self._build_header())

        scroll = QScrollArea(self)
        scroll.setObjectName("protocolDetailsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll)
        content.setObjectName("protocolDetailsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        content_layout.addWidget(self._build_common_group())
        content_layout.addWidget(self._build_protocol_group())
        content_layout.addWidget(self._build_payload_group())
        content_layout.addWidget(self._build_all_fields_group())
        if message.error or (message.fields or {}).get("decode_error"):
            content_layout.addWidget(self._build_error_group())
        content_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.setObjectName("protocolDetailsButtons")
        buttons.rejected.connect(self.close)
        root.addWidget(buttons)

    def _build_header(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("protocolDetailsHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        title = QLabel(self.message.name or "Wiadomość logiczna", frame)
        title.setObjectName("protocolDetailsTitle")
        font = title.font()
        font.setBold(True)
        font.setPointSize(max(10, font.pointSize() + 2))
        title.setFont(font)
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(title, 1)

        protocol = QLabel(protocol_label(self.protocol_key), frame)
        protocol.setObjectName("protocolDetailsKind")
        protocol.setProperty("protocol", self.protocol_key)
        font = protocol.font()
        font.setBold(True)
        protocol.setFont(font)
        layout.addWidget(protocol)

        state = QLabel("COMPLETE" if self.message.complete else "INCOMPLETE", frame)
        state.setObjectName("protocolDetailsState")
        state.setProperty("complete", bool(self.message.complete))
        font = state.font()
        font.setBold(True)
        state.setFont(font)
        layout.addWidget(state)
        return frame

    def _build_common_group(self) -> QGroupBox:
        group = QGroupBox("Identyfikacja i transport", self)
        group.setObjectName("protocolCommonGroup")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        fields = self.message.fields or {}
        duration_ms = (
            self.message.last_timestamp_ns - self.message.first_timestamp_ns
        ) / 1_000_000
        rows = (
            ("Czas początku", format_logical_time(self.message.first_timestamp_ns)),
            ("Czas końca", format_logical_time(self.message.last_timestamp_ns)),
            ("Czas składania", f"{duration_ms:.6f} ms"),
            ("CAN ID / PGN", format_message_id(self.message)),
            ("Nadawca", sender_text(self.message)),
            ("Odbiorca", _address(self.message.destination_address)),
            ("Protokół", protocol_label(self.protocol_key)),
            ("Transport", str(self.message.transport).upper()),
            ("Kierunek", _display(fields.get("direction"))),
            ("DLC / payload", f"{len(self.message.payload)} B"),
            ("Liczba ramek", str(self.message.frame_count)),
            ("Sekwencje ramek", ", ".join(str(value) for value in self.message.frame_sequences) or "—"),
            ("Pewność klasyfikacji", f"{self.message.confidence:.3f}"),
        )
        _add_form_rows(form, rows)
        return group

    def _build_protocol_group(self) -> QGroupBox:
        if self.protocol_key == "uds":
            return self._build_uds_group()
        if self.protocol_key == "dbc":
            return self._build_dbc_group()
        if self.protocol_key == "j1939":
            return self._build_j1939_group()
        if self.protocol_key == "canopen":
            return self._build_canopen_group()
        return self._build_unknown_group()

    def _build_uds_group(self) -> QGroupBox:
        group = QGroupBox("UDS — dane zdekodowane", self)
        group.setObjectName("udsDetailsGroup")
        layout = QVBoxLayout(group)
        form = QFormLayout()
        fields = self.message.fields or {}
        specs = (
            ("Usługa", "service_name"),
            ("Typ odpowiedzi", "response_type"),
            ("SID", "service_id_hex"),
            ("Bazowy SID", "base_service_id_hex"),
            ("Żądana usługa", "requested_service_name"),
            ("NRC", "negative_response_name"),
            ("Kod NRC", "negative_response_code_hex"),
            ("Response pending", "response_pending"),
            ("Podfunkcja", "subfunction_hex"),
            ("Sesja diagnostyczna", "diagnostic_session_type_hex"),
            ("P2ServerMax", "p2_server_max_ms"),
            ("P2*ServerMax", "p2_star_server_max_ms"),
            ("DID-y", "did_list_hex"),
            ("DID", "did_hex"),
            ("Dane ASCII", "data_record_ascii"),
            ("Dane HEX", "data_record_hex"),
            ("SecurityAccess", "security_access_type"),
            ("Poziom zabezpieczeń", "security_level"),
            ("Seed", "seed_hex"),
            ("Key", "key_hex"),
            ("Routine ID", "routine_id_hex"),
            ("Routine option", "routine_option_record_hex"),
            ("Routine status", "routine_status_record_hex"),
            ("Adres pamięci", "memory_address_hex"),
            ("Rozmiar pamięci", "memory_size_hex"),
            ("Maks. długość bloku", "max_number_of_block_length"),
            ("Licznik bloku", "block_sequence_counter"),
            ("Dane transferu", "transfer_data_hex"),
            ("Odpowiedź transferu", "transfer_response_parameter_record_hex"),
            ("Liczba DTC", "dtc_count"),
            ("DTC", "dtc_summary"),
            ("Grupa DTC", "group_of_dtc_hex"),
        )
        _add_selected_fields(form, fields, specs)
        layout.addLayout(form)
        entries = fields.get("dtc_entries")
        if isinstance(entries, list) and entries:
            layout.addWidget(_mapping_table(entries, ("dtc_hex", "status_hex"), ("DTC", "Status"), group, "dtcEntryTable"))
        return group

    def _build_dbc_group(self) -> QGroupBox:
        group = QGroupBox("DBC — wiadomość i sygnały", self)
        group.setObjectName("dbcDetailsGroup")
        layout = QVBoxLayout(group)
        fields = self.message.fields or {}
        form = QFormLayout()
        specs = (
            ("Plik DBC", "dbc_file"),
            ("Wiadomość", "dbc_message"),
            ("Nadawca", "sender_name"),
            ("Tryb dopasowania", "dbc_match_mode"),
            ("Punktacja dopasowania", "dbc_match_score"),
            ("Deklarowana długość", "declared_length"),
            ("Okres", "cycle_time_ms"),
            ("Błąd dekodowania", "decode_error"),
        )
        _add_selected_fields(form, fields, specs)
        layout.addLayout(form)

        signals = fields.get("signals")
        if isinstance(signals, dict) and signals:
            units = fields.get("signal_units")
            unit_map = units if isinstance(units, dict) else {}
            table = QTableWidget(len(signals), 3, group)
            table.setObjectName("dbcSignalTable")
            table.setHorizontalHeaderLabels(("Sygnał", "Wartość", "Jednostka"))
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.verticalHeader().hide()
            for row, (name, value) in enumerate(signals.items()):
                table.setItem(row, 0, QTableWidgetItem(str(name)))
                table.setItem(row, 1, QTableWidgetItem(_display(value)))
                table.setItem(row, 2, QTableWidgetItem(str(unit_map.get(name) or "")))
            table.resizeColumnsToContents()
            table.horizontalHeader().setStretchLastSection(True)
            table.setMinimumHeight(min(360, 55 + 25 * len(signals)))
            layout.addWidget(table)
        return group

    def _build_j1939_group(self) -> QGroupBox:
        group = QGroupBox("J1939 — identyfikator i transport", self)
        group.setObjectName("j1939DetailsGroup")
        form = QFormLayout(group)
        specs = (
            ("PGN", "pgn_hex"),
            ("Nazwa PGN", "pgn_name"),
            ("Priorytet", "priority"),
            ("PDU", "pdu_type"),
            ("PF", "pdu_format"),
            ("PS", "pdu_specific"),
            ("Source Address", "source_address"),
            ("Destination Address", "destination_address"),
            ("Kierunek", "direction"),
            ("Deklarowany payload", "declared_payload_length"),
            ("Deklarowane pakiety", "declared_packet_count"),
            ("Odebrane pakiety", "received_packet_count"),
        )
        _add_selected_fields(form, self.message.fields or {}, specs)
        return group

    def _build_canopen_group(self) -> QGroupBox:
        group = QGroupBox("CANopen — obiekt komunikacyjny", self)
        group.setObjectName("canopenDetailsGroup")
        form = QFormLayout(group)
        specs = (
            ("Funkcja", "canopen_function"),
            ("Node ID", "node_id"),
            ("COB-ID", "cob_id"),
            ("Command specifier", "command_specifier"),
            ("Index", "index_hex"),
            ("Subindex", "subindex"),
            ("NMT command", "nmt_command"),
            ("Target node", "target_node"),
            ("NMT state", "nmt_state"),
        )
        _add_selected_fields(form, self.message.fields or {}, specs)
        return group

    def _build_unknown_group(self) -> QGroupBox:
        group = QGroupBox("Dane własne / nierozpoznane", self)
        group.setObjectName("proprietaryDetailsGroup")
        form = QFormLayout(group)
        fields = self.message.fields or {}
        candidate = fields.get("j1939_identifier_candidate")
        if isinstance(candidate, dict):
            _add_form_rows(
                form,
                ((f"J1939 candidate — {_friendly_key(key)}", _display(value)) for key, value in candidate.items()),
            )
        specs = (
            ("Błąd dekodowania", "decode_error"),
            ("Kompletność", "complete"),
            ("Długość payloadu", "payload_length"),
            ("Liczba ramek", "frame_count"),
        )
        _add_selected_fields(form, fields, specs)
        return group

    def _build_payload_group(self) -> QGroupBox:
        group = QGroupBox("Payload", self)
        group.setObjectName("protocolPayloadGroup")
        layout = QVBoxLayout(group)
        payload = QPlainTextEdit(group)
        payload.setObjectName("rawPayloadView")
        payload.setReadOnly(True)
        payload.setPlainText(self.message.payload_hex or "—")
        payload.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        payload.setMaximumHeight(105)
        layout.addWidget(payload)
        return group

    def _build_all_fields_group(self) -> QGroupBox:
        group = QGroupBox("Wszystkie pola dekodera", self)
        group.setObjectName("protocolAllFieldsGroup")
        layout = QVBoxLayout(group)
        editor = QPlainTextEdit(group)
        editor.setObjectName("decodedFieldsJson")
        editor.setReadOnly(True)
        editor.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        editor.setPlainText(
            json.dumps(
                self.message.fields or {},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        editor.setMinimumHeight(180)
        layout.addWidget(editor)
        return group

    def _build_error_group(self) -> QGroupBox:
        group = QGroupBox("Błędy", self)
        group.setObjectName("protocolErrorGroup")
        layout = QVBoxLayout(group)
        errors = [self.message.error]
        decode_error = (self.message.fields or {}).get("decode_error")
        if decode_error:
            errors.append(str(decode_error))
        label = QLabel("\n".join(value for value in errors if value), group)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        return group


def _mapping_table(
    rows: list[dict[str, object]],
    keys: tuple[str, ...],
    headers: tuple[str, ...],
    parent: QWidget,
    object_name: str,
) -> QTableWidget:
    table = QTableWidget(len(rows), len(keys), parent)
    table.setObjectName(object_name)
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().hide()
    for row_index, row in enumerate(rows):
        for column, key in enumerate(keys):
            table.setItem(row_index, column, QTableWidgetItem(_display(row.get(key))))
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)
    table.setMinimumHeight(min(300, 55 + 25 * len(rows)))
    return table


def _add_selected_fields(
    form: QFormLayout,
    fields: dict[str, object],
    specs: Iterable[tuple[str, str]],
) -> None:
    rows = []
    for label, key in specs:
        value = fields.get(key)
        if value in (None, ""):
            continue
        rows.append((label, _display(value)))
    _add_form_rows(form, rows)


def _add_form_rows(
    form: QFormLayout,
    rows: Iterable[tuple[str, str]],
) -> None:
    for title, value in rows:
        label = QLabel(str(value))
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(f"{title}:", label)


def _display(value: object) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Tak" if value else "Nie"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def _address(value: int | None) -> str:
    return "—" if value is None else f"0x{value:02X}"


def _friendly_key(key: object) -> str:
    return " ".join(part.capitalize() for part in str(key).split("_"))
