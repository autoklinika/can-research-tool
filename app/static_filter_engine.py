from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from .filters import (
    CanFrameRecord,
    FilterCompiler,
    FilterContext,
    FilterPreset,
    FilterResult,
    LogicalOperator,
    MatchState,
    ValidationIssue,
)
from .static_filter_patterns import CanIdPattern, PayloadMatchMode, PayloadPattern


class StaticFilterField(StrEnum):
    CHANNEL = "channel"
    RTR = "rtr"
    ERROR_FRAME = "error_frame"
    PAYLOAD = "payload"


class StaticFilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    BETWEEN = "between"
    OUTSIDE = "outside"
    IN = "in"
    NOT_IN = "not_in"
    CAN_ID_PATTERN = "can_id_pattern"
    PAYLOAD_EXACT = "payload_exact"
    PAYLOAD_PREFIX = "payload_prefix"
    PAYLOAD_CONTAINS = "payload_contains"


@dataclass(frozen=True, slots=True)
class StaticCanFrameRecord:
    can_id: int
    extended: bool
    dlc: int
    relative_time_us: int = 0
    channel: int = 0
    rtr: bool = False
    error_frame: bool = False
    payload: bytes = b""

    def __post_init__(self) -> None:
        payload = bytes(self.payload)
        object.__setattr__(self, "payload", payload)
        if not 0 <= self.channel:
            raise ValueError("channel cannot be negative")
        if not 0 <= self.dlc <= 64:
            raise ValueError("DLC must be in range 0-64")
        if len(payload) > 64:
            raise ValueError("raw CAN payload cannot exceed 64 bytes")

    @classmethod
    def from_legacy(
        cls,
        frame: CanFrameRecord,
        *,
        rtr: bool = False,
        error_frame: bool = False,
        payload: bytes = b"",
    ) -> StaticCanFrameRecord:
        return cls(
            can_id=frame.can_id,
            extended=frame.extended,
            dlc=frame.dlc,
            relative_time_us=frame.relative_time_us,
            channel=frame.channel,
            rtr=rtr,
            error_frame=error_frame,
            payload=payload,
        )


@dataclass(frozen=True, slots=True)
class StaticFilterContext:
    legacy: FilterContext
    values: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_frame(
        cls,
        frame: StaticCanFrameRecord | CanFrameRecord,
    ) -> StaticFilterContext:
        if isinstance(frame, CanFrameRecord):
            frame = StaticCanFrameRecord.from_legacy(frame)
        legacy_record = CanFrameRecord(
            can_id=frame.can_id,
            extended=frame.extended,
            dlc=frame.dlc,
            relative_time_us=frame.relative_time_us,
            channel=frame.channel,
        )
        return cls(
            legacy=FilterContext.from_frame(legacy_record),
            values={
                StaticFilterField.CHANNEL.value: frame.channel,
                StaticFilterField.RTR.value: frame.rtr,
                StaticFilterField.ERROR_FRAME.value: frame.error_frame,
                StaticFilterField.PAYLOAD.value: frame.payload,
            },
        )

    def resolve(self, field_name: str) -> tuple[bool, Any]:
        if field_name in self.values:
            return True, self.values[field_name]
        return self.legacy.resolve_name(field_name) if hasattr(self.legacy, "resolve_name") else (
            (True, self.legacy.values[field_name])
            if field_name in self.legacy.values
            else (False, None)
        )


class StaticFilterCompiler:
    """Backward-compatible v2 compiler for advanced static conditions.

    Legacy conditions are delegated to the proven v1 ``FilterCompiler``.
    Only v2 fields and operators are handled here.
    """

    def __init__(self, max_depth: int = 12) -> None:
        self.max_depth = max_depth
        self.legacy = FilterCompiler(max_depth=max_depth)

    def validate(self, preset: FilterPreset) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not preset.name.strip():
            issues.append(ValidationIssue("preset.name", "Nazwa filtra nie może być pusta."))
        self._validate_node(preset, preset.root, "root", 0, issues)
        return issues

    def evaluate(
        self,
        preset: FilterPreset,
        record: StaticCanFrameRecord | CanFrameRecord | StaticFilterContext,
    ) -> FilterResult:
        context = record if isinstance(record, StaticFilterContext) else StaticFilterContext.from_frame(record)
        issues = self.validate(preset)
        if issues:
            return FilterResult(MatchState.UNAVAILABLE, issues[0].message)
        return self._evaluate_node(preset, preset.root, context)

    def _validate_node(
        self,
        preset: FilterPreset,
        node: Mapping[str, Any],
        path: str,
        depth: int,
        issues: list[ValidationIssue],
    ) -> None:
        if depth > self.max_depth:
            issues.append(ValidationIssue(path, f"Maksymalna głębokość filtra to {self.max_depth}."))
            return
        node_type = str(node.get("type", ""))
        if node_type == "group":
            try:
                operator = LogicalOperator(str(node.get("operator", "")))
            except ValueError:
                issues.append(ValidationIssue(path, "Nieznany operator grupy."))
                return
            children = node.get("children")
            if not isinstance(children, list):
                issues.append(ValidationIssue(path, "Pole children musi być listą."))
                return
            if operator == LogicalOperator.NOT and len(children) != 1:
                issues.append(ValidationIssue(path, "Grupa NOT musi zawierać dokładnie jeden element."))
            if operator in {LogicalOperator.AND, LogicalOperator.OR} and not children:
                issues.append(ValidationIssue(path, "Grupa logiczna nie może być pusta."))
            for index, child in enumerate(children):
                if not isinstance(child, Mapping):
                    issues.append(ValidationIssue(f"{path}.children[{index}]", "Węzeł musi być obiektem."))
                else:
                    self._validate_node(
                        preset,
                        child,
                        f"{path}.children[{index}]",
                        depth + 1,
                        issues,
                    )
            return
        if node_type != "condition":
            issues.append(ValidationIssue(path, "Węzeł musi mieć typ group albo condition."))
            return

        field_name = str(node.get("field", ""))
        operator_name = str(node.get("operator", ""))
        values = node.get("values")
        if not isinstance(values, list):
            issues.append(ValidationIssue(path, "Pole values musi być listą."))
            return

        if self._is_v2_condition(field_name, operator_name):
            self._validate_v2_condition(field_name, operator_name, values, path, issues)
            return

        legacy_preset = FilterPreset.from_mapping(preset.to_mapping())
        legacy_preset.root = dict(node)
        for issue in self.legacy.validate(legacy_preset):
            suffix = issue.path.removeprefix("root")
            issues.append(ValidationIssue(f"{path}{suffix}", issue.message))

    @staticmethod
    def _is_v2_condition(field_name: str, operator_name: str) -> bool:
        return field_name in {item.value for item in StaticFilterField} or operator_name in {
            StaticFilterOperator.CAN_ID_PATTERN.value,
            StaticFilterOperator.PAYLOAD_EXACT.value,
            StaticFilterOperator.PAYLOAD_PREFIX.value,
            StaticFilterOperator.PAYLOAD_CONTAINS.value,
        }

    @staticmethod
    def _validate_v2_condition(
        field_name: str,
        operator_name: str,
        values: list[Any],
        path: str,
        issues: list[ValidationIssue],
    ) -> None:
        try:
            operator = StaticFilterOperator(operator_name)
        except ValueError:
            issues.append(ValidationIssue(path, "Nieznany operator warunku statycznego."))
            return
        required = 2 if operator in {StaticFilterOperator.BETWEEN, StaticFilterOperator.OUTSIDE} else 1
        if len(values) < required:
            issues.append(ValidationIssue(path, "Warunek nie zawiera wymaganej liczby wartości."))
            return
        try:
            if operator == StaticFilterOperator.CAN_ID_PATTERN:
                if field_name != "can_id":
                    raise ValueError("operator maski CAN ID wymaga pola can_id")
                CanIdPattern.parse(str(values[0]))
            elif operator in {
                StaticFilterOperator.PAYLOAD_EXACT,
                StaticFilterOperator.PAYLOAD_PREFIX,
                StaticFilterOperator.PAYLOAD_CONTAINS,
            }:
                if field_name != StaticFilterField.PAYLOAD.value:
                    raise ValueError("operator payloadu wymaga pola payload")
                PayloadPattern.parse(str(values[0]), mode=_payload_mode(operator))
            elif field_name == StaticFilterField.CHANNEL.value:
                normalized = [_parse_int(value) for value in values]
                if any(value < 0 for value in normalized):
                    raise ValueError("kanał CAN nie może być ujemny")
            elif field_name in {
                StaticFilterField.RTR.value,
                StaticFilterField.ERROR_FRAME.value,
            }:
                for value in values:
                    _parse_bool(value)
            elif field_name == StaticFilterField.PAYLOAD.value:
                raise ValueError("pole payload wymaga operatora payload_exact/prefix/contains")
        except (TypeError, ValueError) as exc:
            issues.append(ValidationIssue(path, f"Nieprawidłowa wartość: {exc}"))

    def _evaluate_node(
        self,
        preset: FilterPreset,
        node: Mapping[str, Any],
        context: StaticFilterContext,
    ) -> FilterResult:
        if node["type"] == "condition":
            return self._evaluate_condition(preset, node, context)
        operator = LogicalOperator(str(node["operator"]))
        children = [self._evaluate_node(preset, child, context) for child in node["children"]]
        if operator == LogicalOperator.NOT:
            child = children[0]
            if child.state == MatchState.UNAVAILABLE:
                return child
            return FilterResult(MatchState.NO_MATCH if child.state == MatchState.MATCH else MatchState.MATCH)
        if operator == LogicalOperator.AND:
            if any(result.state == MatchState.NO_MATCH for result in children):
                return FilterResult(MatchState.NO_MATCH)
            unavailable = next((result for result in children if result.state == MatchState.UNAVAILABLE), None)
            return unavailable or FilterResult(MatchState.MATCH)
        if any(result.state == MatchState.MATCH for result in children):
            return FilterResult(MatchState.MATCH)
        unavailable = next((result for result in children if result.state == MatchState.UNAVAILABLE), None)
        return unavailable or FilterResult(MatchState.NO_MATCH)

    def _evaluate_condition(
        self,
        preset: FilterPreset,
        node: Mapping[str, Any],
        context: StaticFilterContext,
    ) -> FilterResult:
        field_name = str(node["field"])
        operator_name = str(node["operator"])
        if not self._is_v2_condition(field_name, operator_name):
            legacy_preset = FilterPreset.from_mapping(preset.to_mapping())
            legacy_preset.root = dict(node)
            return self.legacy.evaluate_context(legacy_preset, context.legacy)

        available, actual = context.resolve(field_name)
        if not available:
            return FilterResult(MatchState.UNAVAILABLE, f"Pole {field_name} nie jest dostępne w tym kontekście.")
        try:
            operator = StaticFilterOperator(operator_name)
            values = list(node["values"])
            if operator == StaticFilterOperator.CAN_ID_PATTERN:
                matched = CanIdPattern.parse(str(values[0])).matches(int(actual))
            elif operator in {
                StaticFilterOperator.PAYLOAD_EXACT,
                StaticFilterOperator.PAYLOAD_PREFIX,
                StaticFilterOperator.PAYLOAD_CONTAINS,
            }:
                matched = PayloadPattern.parse(str(values[0]), mode=_payload_mode(operator)).matches(bytes(actual))
            else:
                normalized_actual, normalized_values = _normalize_static(field_name, actual, values)
                matched = _compare(normalized_actual, operator, normalized_values)
        except (TypeError, ValueError) as exc:
            return FilterResult(MatchState.UNAVAILABLE, f"Pole {field_name} ma nieprawidłową wartość: {exc}")
        return FilterResult(MatchState.MATCH if matched else MatchState.NO_MATCH)


def _payload_mode(operator: StaticFilterOperator) -> PayloadMatchMode:
    return {
        StaticFilterOperator.PAYLOAD_EXACT: PayloadMatchMode.EXACT,
        StaticFilterOperator.PAYLOAD_PREFIX: PayloadMatchMode.PREFIX,
        StaticFilterOperator.PAYLOAD_CONTAINS: PayloadMatchMode.CONTAINS,
    }[operator]


def _normalize_static(field_name: str, actual: Any, values: list[Any]) -> tuple[Any, list[Any]]:
    if field_name in {StaticFilterField.RTR.value, StaticFilterField.ERROR_FRAME.value}:
        return _parse_bool(actual), [_parse_bool(value) for value in values]
    if field_name == StaticFilterField.CHANNEL.value:
        return _parse_int(actual), [_parse_int(value) for value in values]
    raise ValueError(f"unsupported static field: {field_name}")


def _parse_int(value: Any) -> int:
    if isinstance(value, str):
        text = value.strip().lower().replace("_", "")
        return int(text, 16) if text.startswith("0x") else int(text, 10)
    return int(value)


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "tak"}:
        return True
    if normalized in {"0", "false", "no", "nie"}:
        return False
    raise ValueError("wartość logiczna musi oznaczać tak albo nie")


def _compare(actual: Any, operator: StaticFilterOperator, values: list[Any]) -> bool:
    if operator == StaticFilterOperator.EQ:
        return actual == values[0]
    if operator == StaticFilterOperator.NE:
        return actual != values[0]
    if operator == StaticFilterOperator.GT:
        return actual > values[0]
    if operator == StaticFilterOperator.GE:
        return actual >= values[0]
    if operator == StaticFilterOperator.LT:
        return actual < values[0]
    if operator == StaticFilterOperator.LE:
        return actual <= values[0]
    if operator == StaticFilterOperator.BETWEEN:
        return values[0] <= actual <= values[1]
    if operator == StaticFilterOperator.OUTSIDE:
        return actual < values[0] or actual > values[1]
    if operator == StaticFilterOperator.IN:
        return actual in values
    if operator == StaticFilterOperator.NOT_IN:
        return actual not in values
    raise ValueError(f"unsupported operator: {operator}")
