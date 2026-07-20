from __future__ import annotations

from dataclasses import dataclass

from app.filters import FilterField, ProtocolFilterField


@dataclass(frozen=True, slots=True)
class FilterFieldChoice:
    field: str
    label: str
    hint: str
    default_value: str


_CHOICES = (
    (
        "CAN",
        FilterField.CAN_ID,
        "CAN ID",
        "HEX: 0x18FEAE30. Listy i zakresy rozdziel przecinkami.",
        "0x18FEAE30",
    ),
    ("CAN", FilterField.FRAME_FORMAT, "STD / EXT", "Dozwolone wartości: std albo ext.", "ext"),
    ("CAN", FilterField.DLC, "DLC", "Zakres 0–64. Pole dotyczy surowych ramek.", "8"),
    (
        "CAN",
        FilterField.RELATIVE_TIME_US,
        "Czas względny [µs]",
        "Czas od początku sesji w mikrosekundach.",
        "0",
    ),
    ("Wspólne", ProtocolFilterField.PROTOCOL, "Protokół", "Np. uds, j1939, dbc, unknown.", "uds"),
    (
        "Wspólne",
        ProtocolFilterField.TRANSPORT,
        "Transport",
        "Np. raw, isotp, j1939-bam, j1939-rts-cts.",
        "isotp",
    ),
    (
        "Wspólne",
        ProtocolFilterField.MESSAGE_NAME,
        "Nazwa wiadomości",
        "Porównanie tekstowe nie rozróżnia wielkości liter.",
        "ReadDataByIdentifier",
    ),
    (
        "Wspólne",
        ProtocolFilterField.COMPLETE,
        "Kompletna",
        "Wartości logiczne: tak/nie, true/false, 1/0.",
        "tak",
    ),
    (
        "Wspólne",
        ProtocolFilterField.ERROR,
        "Błąd transportu",
        "Pusty tekst oznacza brak błędu; operator różni się wykrywa dowolny błąd.",
        "",
    ),
    ("Wspólne", ProtocolFilterField.CONFIDENCE, "Pewność klasyfikacji", "Zakres 0–1.", "1.0"),
    (
        "Wspólne",
        ProtocolFilterField.SOURCE_FRAME_COUNT,
        "Liczba ramek źródłowych",
        "1 oznacza wiadomość jednoramkową.",
        "1",
    ),
    (
        "Wspólne",
        ProtocolFilterField.PAYLOAD_LENGTH,
        "Długość payloadu",
        "Długość zrekonstruowanego payloadu w bajtach.",
        "8",
    ),
    (
        "Wspólne",
        ProtocolFilterField.DECLARED_PAYLOAD_LENGTH,
        "Deklarowana długość payloadu",
        "Wartość z nagłówka transportowego, jeśli dostępna.",
        "8",
    ),
    (
        "Wspólne",
        ProtocolFilterField.RECEIVED_PAYLOAD_LENGTH,
        "Odebrana długość payloadu",
        "Liczba faktycznie odebranych bajtów.",
        "8",
    ),
    ("J1939", ProtocolFilterField.PGN, "PGN", "Zakres 0x00000–0x3FFFF.", "0xFECA"),
    (
        "J1939",
        ProtocolFilterField.PGN_NAME,
        "Nazwa PGN",
        "Np. Active Diagnostic Trouble Codes (DM1).",
        "DM1",
    ),
    ("J1939", ProtocolFilterField.SOURCE_ADDRESS, "Source Address", "Zakres 0x00–0xFF.", "0x30"),
    (
        "J1939",
        ProtocolFilterField.DESTINATION_ADDRESS,
        "Destination Address",
        "Zakres 0x00–0xFF.",
        "0xFF",
    ),
    ("J1939", ProtocolFilterField.PRIORITY, "Priority", "Zakres 0–7.", "6"),
    ("J1939", ProtocolFilterField.EXTENDED_DATA_PAGE, "Extended Data Page", "0 albo 1.", "0"),
    ("J1939", ProtocolFilterField.DATA_PAGE, "Data Page", "0 albo 1.", "0"),
    ("J1939", ProtocolFilterField.PDU_FORMAT, "PDU Format", "Zakres 0x00–0xFF.", "0xFE"),
    ("J1939", ProtocolFilterField.PDU_SPECIFIC, "PDU Specific", "Zakres 0x00–0xFF.", "0xCA"),
    (
        "J1939",
        ProtocolFilterField.PDU_TYPE,
        "PDU1 / PDU2",
        "Dozwolone wartości: pdu1 albo pdu2.",
        "pdu2",
    ),
    ("J1939", ProtocolFilterField.BROADCAST, "Broadcast", "Wartości logiczne: tak/nie.", "tak"),
    (
        "J1939",
        ProtocolFilterField.DESTINATION_SPECIFIC,
        "Destination-specific",
        "Wartości logiczne: tak/nie.",
        "nie",
    ),
    (
        "J1939",
        ProtocolFilterField.J1939_TRANSPORT,
        "Transport J1939",
        "single-frame, bam albo rts-cts.",
        "bam",
    ),
    ("J1939", ProtocolFilterField.J1939_IS_TP, "J1939 TP", "Wartości logiczne: tak/nie.", "tak"),
    (
        "J1939",
        ProtocolFilterField.DECLARED_PACKET_COUNT,
        "Deklarowana liczba pakietów",
        "Liczba pakietów zadeklarowana przez TP.CM.",
        "2",
    ),
    (
        "J1939",
        ProtocolFilterField.RECEIVED_PACKET_COUNT,
        "Odebrana liczba pakietów",
        "Liczba odebranych pakietów TP.DT.",
        "2",
    ),
    (
        "ISO-TP",
        ProtocolFilterField.ADDRESSING,
        "Typ adresowania",
        "Np. normal-11bit albo normal-fixed-29bit.",
        "normal-11bit",
    ),
    (
        "ISO-TP",
        ProtocolFilterField.ISOTP_FRAMING,
        "Single / Multi Frame",
        "Dozwolone wartości: single-frame albo multi-frame.",
        "single-frame",
    ),
    (
        "ISO-TP",
        ProtocolFilterField.ISOTP_HAS_ERROR,
        "Błąd ISO-TP",
        "Wartości logiczne: tak/nie.",
        "nie",
    ),
    ("UDS", ProtocolFilterField.SID, "SID", "Surowy SID, np. 0x22, 0x62 albo 0x7F.", "0x22"),
    (
        "UDS",
        ProtocolFilterField.BASE_SID,
        "Bazowy SID",
        "SID usługi bez offsetu odpowiedzi 0x40.",
        "0x22",
    ),
    (
        "UDS",
        ProtocolFilterField.DIRECTION,
        "Kierunek UDS",
        "request, positive-response albo negative-response.",
        "request",
    ),
    (
        "UDS",
        ProtocolFilterField.RESPONSE_TYPE,
        "Typ odpowiedzi",
        "request, positive-response albo negative-response.",
        "positive-response",
    ),
    (
        "UDS",
        ProtocolFilterField.SERVICE_NAME,
        "Nazwa usługi",
        "Np. ReadDataByIdentifier.",
        "ReadDataByIdentifier",
    ),
    (
        "UDS",
        ProtocolFilterField.REQUESTED_SERVICE_NAME,
        "Żądana usługa",
        "Nazwa usługi wskazana przez odpowiedź negatywną.",
        "SecurityAccess",
    ),
    ("UDS", ProtocolFilterField.NRC, "NRC", "Zakres 0x00–0xFF.", "0x31"),
    (
        "UDS",
        ProtocolFilterField.NRC_NAME,
        "Nazwa NRC",
        "Np. requestOutOfRange albo invalidKey.",
        "requestOutOfRange",
    ),
    ("UDS", ProtocolFilterField.DID, "DID", "Zakres 0x0000–0xFFFF.", "0xF190"),
    ("UDS", ProtocolFilterField.ROUTINE_ID, "Routine ID", "Zakres 0x0000–0xFFFF.", "0x0203"),
    (
        "UDS",
        ProtocolFilterField.SUBFUNCTION,
        "Subfunction",
        "Zakres 0x00–0x7F; bit suppress-positive-response jest osobnym polem.",
        "0x01",
    ),
    (
        "UDS",
        ProtocolFilterField.SUPPRESS_POSITIVE_RESPONSE,
        "Suppress positive response",
        "Wartości logiczne: tak/nie.",
        "nie",
    ),
    (
        "UDS",
        ProtocolFilterField.SECURITY_ACCESS_TYPE,
        "Faza SecurityAccess",
        "request-seed albo send-key.",
        "request-seed",
    ),
    ("UDS", ProtocolFilterField.SECURITY_LEVEL, "Poziom SecurityAccess", "Zakres 1–63.", "1"),
    (
        "UDS",
        ProtocolFilterField.BLOCK_SEQUENCE_COUNTER,
        "Block Sequence Counter",
        "Zakres 0x00–0xFF.",
        "0x01",
    ),
)

FILTER_FIELD_CHOICES: tuple[FilterFieldChoice, ...] = tuple(
    FilterFieldChoice(
        field=field.value,
        label=f"{category} — {label}",
        hint=hint,
        default_value=default,
    )
    for category, field, label, hint, default in _CHOICES
)

FIELD_LABELS = {choice.field: choice.label for choice in FILTER_FIELD_CHOICES}
FIELD_HINTS = {choice.field: choice.hint for choice in FILTER_FIELD_CHOICES}
FIELD_DEFAULTS = {choice.field: choice.default_value for choice in FILTER_FIELD_CHOICES}
