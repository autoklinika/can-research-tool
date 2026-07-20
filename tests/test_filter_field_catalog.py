from app.filters import FilterField, ProtocolFilterField
from gui.filter_field_catalog import FILTER_FIELD_CHOICES, FIELD_DEFAULTS, FIELD_HINTS, FIELD_LABELS


def test_gui_catalog_exposes_every_filter_field_once() -> None:
    expected = {field.value for field in FilterField} | {
        field.value for field in ProtocolFilterField
    }
    actual = [choice.field for choice in FILTER_FIELD_CHOICES]

    assert len(actual) == len(set(actual))
    assert set(actual) == expected
    assert set(FIELD_LABELS) == expected
    assert set(FIELD_HINTS) == expected
    assert set(FIELD_DEFAULTS) == expected


def test_gui_catalog_contains_protocol_sections() -> None:
    labels = tuple(FIELD_LABELS.values())

    assert any(label.startswith("J1939 —") for label in labels)
    assert any(label.startswith("ISO-TP —") for label in labels)
    assert any(label.startswith("UDS —") for label in labels)
