from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.filters import FilterField, FilterOperator
from app.static_filter_engine import StaticFilterField, StaticFilterOperator

from .filter_field_catalog import FilterFieldChoice


STATIC_FILTER_FIELD_CHOICES: tuple[FilterFieldChoice, ...] = (
    FilterFieldChoice(
        field=StaticFilterField.CHANNEL.value,
        label="CAN — Kanał",
        hint="Numer kanału interfejsu CAN. Wartość całkowita od 0.",
        default_value="0",
    ),
    FilterFieldChoice(
        field=StaticFilterField.RTR.value,
        label="CAN — RTR",
        hint="Ramka Remote Transmission Request: tak/nie, true/false albo 1/0.",
        default_value="nie",
    ),
    FilterFieldChoice(
        field=StaticFilterField.ERROR_FRAME.value,
        label="CAN — Error frame",
        hint="Sprzętowa ramka błędu CAN: tak/nie, true/false albo 1/0.",
        default_value="nie",
    ),
    FilterFieldChoice(
        field=StaticFilterField.PAYLOAD.value,
        label="CAN — Payload / maska",
        hint=(
            "Bajty HEX, np. 62 F1 90. Wildcard całego bajtu: ?? lub **. "
            "Maska bitowa bajtu: wartość/maska, np. A0/F0. Maksymalnie 64 bajty."
        ),
        default_value="62 F1 90",
    ),
)

STATIC_FIELD_LABELS = {choice.field: choice.label for choice in STATIC_FILTER_FIELD_CHOICES}
STATIC_FIELD_HINTS = {choice.field: choice.hint for choice in STATIC_FILTER_FIELD_CHOICES}
STATIC_FIELD_DEFAULTS = {choice.field: choice.default_value for choice in STATIC_FILTER_FIELD_CHOICES}

STATIC_OPERATOR_LABELS: dict[str, str] = {
    StaticFilterOperator.CAN_ID_PATTERN.value: "pasuje do maski / wildcard",
    StaticFilterOperator.PAYLOAD_EXACT.value: "payload dokładnie równy",
    StaticFilterOperator.PAYLOAD_PREFIX.value: "payload zaczyna się od",
    StaticFilterOperator.PAYLOAD_CONTAINS.value: "payload zawiera",
}

_COMMON_OPERATOR_LABELS: dict[str, str] = {
    FilterOperator.EQ.value: "równa się",
    FilterOperator.NE.value: "różni się",
    FilterOperator.GT.value: "większe niż",
    FilterOperator.GE.value: "większe lub równe",
    FilterOperator.LT.value: "mniejsze niż",
    FilterOperator.LE.value: "mniejsze lub równe",
    FilterOperator.BETWEEN.value: "pomiędzy",
    FilterOperator.OUTSIDE.value: "poza zakresem",
    FilterOperator.IN.value: "w zbiorze",
    FilterOperator.NOT_IN.value: "nie w zbiorze",
}

_LEGACY_OPERATORS: tuple[str, ...] = tuple(operator.value for operator in FilterOperator)
_BOOLEAN_OPERATORS = (FilterOperator.EQ.value, FilterOperator.NE.value)
_PAYLOAD_OPERATORS = (
    StaticFilterOperator.PAYLOAD_EXACT.value,
    StaticFilterOperator.PAYLOAD_PREFIX.value,
    StaticFilterOperator.PAYLOAD_CONTAINS.value,
)


def operators_for_field(field_name: str) -> tuple[str, ...]:
    if field_name == FilterField.CAN_ID.value:
        return (*_LEGACY_OPERATORS, StaticFilterOperator.CAN_ID_PATTERN.value)
    if field_name == StaticFilterField.PAYLOAD.value:
        return _PAYLOAD_OPERATORS
    if field_name in {StaticFilterField.RTR.value, StaticFilterField.ERROR_FRAME.value}:
        return _BOOLEAN_OPERATORS
    return _LEGACY_OPERATORS


def default_operator_for_field(field_name: str) -> str:
    if field_name == StaticFilterField.PAYLOAD.value:
        return StaticFilterOperator.PAYLOAD_EXACT.value
    return FilterOperator.EQ.value


def operator_hint(operator_name: str) -> str:
    if operator_name == StaticFilterOperator.CAN_ID_PATTERN.value:
        return (
            "Formaty: dokładny 0x18DAF900, wildcard 0x18DA??F9 albo "
            "jawna maska 0x18DA00F9/0x1FFF00FF."
        )
    if operator_name in _PAYLOAD_OPERATORS:
        return (
            "Wzorzec payloadu obsługuje bajty HEX, wildcard ?? oraz maskę bajtu value/mask."
        )
    return ""


def is_static_condition(node: Mapping[str, Any]) -> bool:
    if node.get("type") == "condition":
        field_name = str(node.get("field", ""))
        operator_name = str(node.get("operator", ""))
        return field_name in {field.value for field in StaticFilterField} or operator_name in {
            StaticFilterOperator.CAN_ID_PATTERN.value,
            StaticFilterOperator.PAYLOAD_EXACT.value,
            StaticFilterOperator.PAYLOAD_PREFIX.value,
            StaticFilterOperator.PAYLOAD_CONTAINS.value,
        }
    children = node.get("children")
    return isinstance(children, list) and any(
        isinstance(child, Mapping) and is_static_condition(child) for child in children
    )


def summarize_static_condition(node: Mapping[str, Any]) -> str:
    if node.get("type") != "condition" or not is_static_condition(node):
        return ""
    field_name = str(node.get("field", ""))
    operator_name = str(node.get("operator", ""))
    field_label = {
        FilterField.CAN_ID.value: "CAN — CAN ID",
        **STATIC_FIELD_LABELS,
    }.get(field_name, field_name)
    operator_label = {
        **_COMMON_OPERATOR_LABELS,
        **STATIC_OPERATOR_LABELS,
    }.get(operator_name, operator_name)
    values = node.get("values")
    rendered = ", ".join(str(value) for value in values) if isinstance(values, list) else "?"
    return f"{field_label}: {operator_label} — {rendered}"
