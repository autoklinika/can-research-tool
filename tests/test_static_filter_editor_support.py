from app.filters import FilterField, FilterOperator
from app.static_filter_engine import StaticFilterField, StaticFilterOperator
from gui.static_filter_editor_support import (
    STATIC_FIELD_DEFAULTS,
    STATIC_FIELD_HINTS,
    STATIC_FIELD_LABELS,
    STATIC_FILTER_FIELD_CHOICES,
    default_operator_for_field,
    operator_hint,
    operators_for_field,
)


def test_static_gui_catalog_exposes_each_v2_field_once() -> None:
    expected = {field.value for field in StaticFilterField}
    actual = [choice.field for choice in STATIC_FILTER_FIELD_CHOICES]

    assert len(actual) == len(set(actual))
    assert set(actual) == expected
    assert set(STATIC_FIELD_LABELS) == expected
    assert set(STATIC_FIELD_HINTS) == expected
    assert set(STATIC_FIELD_DEFAULTS) == expected


def test_operator_catalog_is_field_specific() -> None:
    assert StaticFilterOperator.CAN_ID_PATTERN.value in operators_for_field(
        FilterField.CAN_ID.value
    )
    assert operators_for_field(StaticFilterField.PAYLOAD.value) == (
        StaticFilterOperator.PAYLOAD_EXACT.value,
        StaticFilterOperator.PAYLOAD_PREFIX.value,
        StaticFilterOperator.PAYLOAD_CONTAINS.value,
    )
    assert operators_for_field(StaticFilterField.RTR.value) == (
        FilterOperator.EQ.value,
        FilterOperator.NE.value,
    )
    assert operators_for_field(StaticFilterField.ERROR_FRAME.value) == (
        FilterOperator.EQ.value,
        FilterOperator.NE.value,
    )
    assert FilterOperator.BETWEEN.value in operators_for_field(
        StaticFilterField.CHANNEL.value
    )


def test_payload_uses_safe_default_operator_and_hints() -> None:
    assert (
        default_operator_for_field(StaticFilterField.PAYLOAD.value)
        == StaticFilterOperator.PAYLOAD_EXACT.value
    )
    assert "wildcard" in operator_hint(StaticFilterOperator.CAN_ID_PATTERN.value)
    assert "value/mask" in operator_hint(StaticFilterOperator.PAYLOAD_PREFIX.value)
