from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .filter_preferences import FilterCombinationMode
from .filters import (
    CanFrameRecord,
    FilterCompiler,
    FilterContext,
    FilterField,
    FilterFieldName,
    FilterMode,
    FilterOperator,
    FilterPreset,
    LogicalOperator,
    MatchState,
    ProtocolFilterField,
)
from .live_filters import LiveFilterDecision
from .static_filter_engine import (
    StaticCanFrameRecord,
    StaticFilterCompiler,
    StaticFilterContext,
    StaticFilterField,
    StaticFilterOperator,
)
from .static_filter_patterns import CanIdPattern, PayloadMatchMode, PayloadPattern

_STATIC_FIELD_NAMES = frozenset(field.value for field in StaticFilterField)
_RAW_FIELD_NAMES = frozenset(field.value for field in FilterField) | _STATIC_FIELD_NAMES
_RAW_ONLY_OPERATORS = frozenset(
    {
        StaticFilterOperator.CAN_ID_PATTERN.value,
        StaticFilterOperator.PAYLOAD_EXACT.value,
        StaticFilterOperator.PAYLOAD_PREFIX.value,
        StaticFilterOperator.PAYLOAD_CONTAINS.value,
    }
)


@dataclass(frozen=True, slots=True)
class _CompiledCondition:
    field_name: str
    operator_name: str
    legacy_field: FilterFieldName | None = None
    legacy_operator: FilterOperator | None = None
    static_operator: StaticFilterOperator | None = None
    values: tuple[Any, ...] = ()
    membership: frozenset[Any] | None = None
    can_id_pattern: CanIdPattern | None = None
    payload_pattern: PayloadPattern | None = None

    @property
    def raw_only(self) -> bool:
        return self.field_name in _STATIC_FIELD_NAMES or self.operator_name in _RAW_ONLY_OPERATORS


@dataclass(frozen=True, slots=True)
class _CompiledGroup:
    operator: LogicalOperator
    children: tuple[_CompiledNode, ...]


_CompiledNode = _CompiledCondition | _CompiledGroup


@dataclass(frozen=True, slots=True)
class _CompiledPreset:
    preset: FilterPreset
    root: _CompiledNode | None
    validation_error: str = ""


class StaticCombinedActiveFilterSet:
    """Compiled project filters shared by Live and stored-session views.

    Static patterns are parsed once. Raw frames use a direct field resolver without
    allocating a dictionary context. Conditions introduced by 6A remain neutral in
    logical-message views, where they resolve to ``UNAVAILABLE``.
    """

    def __init__(
        self,
        presets: Iterable[FilterPreset],
        *,
        scope: str | None = None,
        combination_mode: FilterCombinationMode | str = FilterCombinationMode.AND,
    ) -> None:
        self.scope = scope
        self.combination_mode = FilterCombinationMode(str(combination_mode))
        self.presets = tuple(
            preset
            for preset in presets
            if preset.enabled and (scope is None or scope in preset.scope)
        )
        self._compiler = StaticFilterCompiler()
        self._legacy_compiler: FilterCompiler = self._compiler.legacy

        compiled: list[_CompiledPreset] = []
        validation_issues: list[tuple[str, tuple[Any, ...]]] = []
        for preset in self.presets:
            issues = tuple(self._compiler.validate(preset))
            if issues:
                validation_issues.append((preset.name, issues))
                compiled.append(_CompiledPreset(preset, None, issues[0].message))
            else:
                compiled.append(
                    _CompiledPreset(
                        preset,
                        _compile_node(preset.root, self._legacy_compiler),
                    )
                )
        self._compiled_presets = tuple(compiled)
        self.validation_issues = tuple(validation_issues)

    @property
    def active_count(self) -> int:
        return len(self.presets)

    @property
    def active_names(self) -> tuple[str, ...]:
        return tuple(preset.name for preset in self.presets)

    @property
    def affects_visibility(self) -> bool:
        return any(
            preset.mode in {FilterMode.INCLUDE, FilterMode.EXCLUDE}
            for preset in self.presets
        )

    @property
    def affects_raw_visibility(self) -> bool:
        return any(
            preset.mode in {FilterMode.INCLUDE, FilterMode.EXCLUDE}
            and _tree_uses_any_field(preset.root, _RAW_FIELD_NAMES)
            for preset in self.presets
        )

    @property
    def signature(self) -> tuple[object, ...]:
        return (
            self.scope,
            self.combination_mode.value,
            *(
                (
                    preset.id,
                    preset.name,
                    preset.enabled,
                    preset.mode.value,
                    preset.shortcut,
                    tuple(preset.scope),
                    repr(preset.root),
                )
                for preset in self.presets
            ),
        )

    def decide(
        self,
        record: StaticCanFrameRecord | CanFrameRecord | StaticFilterContext | FilterContext,
    ) -> LiveFilterDecision:
        if isinstance(record, StaticCanFrameRecord):
            return self._decide(raw=record)
        if isinstance(record, CanFrameRecord):
            return self._decide(raw=StaticCanFrameRecord.from_legacy(record))
        if isinstance(record, StaticFilterContext):
            return self._decide(context=record)
        return self._decide(context=StaticFilterContext(legacy=record))

    def decide_logical_message(
        self,
        record,
        *,
        relative_time_us: int | None = None,
    ) -> LiveFilterDecision:
        context = FilterContext.from_logical_message(
            record,
            relative_time_us=relative_time_us,
        )
        return self._decide(context=StaticFilterContext(legacy=context))

    def decide_context(self, context: FilterContext) -> LiveFilterDecision:
        return self._decide(context=StaticFilterContext(legacy=context))

    def _decide(
        self,
        *,
        raw: StaticCanFrameRecord | None = None,
        context: StaticFilterContext | None = None,
    ) -> LiveFilterDecision:
        if not self._compiled_presets:
            return LiveFilterDecision(True)

        include_seen = 0
        include_matched = 0
        excluded = False
        highlighted = False
        unavailable: list[str] = []

        for compiled in self._compiled_presets:
            preset = compiled.preset
            if compiled.root is None:
                unavailable.append(
                    f"{preset.name}: {compiled.validation_error or 'nieprawidłowy preset'}"
                )
                continue

            state = (
                _evaluate_raw(compiled.root, raw)
                if raw is not None
                else _evaluate_context(compiled.root, context, self._legacy_compiler)
            )
            if state is MatchState.UNAVAILABLE:
                unavailable.append(
                    f"{preset.name}: warunek niedostępny w tym kontekście"
                )
                continue

            matched = state is MatchState.MATCH
            if preset.mode is FilterMode.INCLUDE:
                include_seen += 1
                include_matched += int(matched)
            elif preset.mode is FilterMode.EXCLUDE:
                excluded = excluded or matched
            elif preset.mode is FilterMode.HIGHLIGHT:
                highlighted = highlighted or matched

            if excluded:
                break
            if (
                self.combination_mode is FilterCombinationMode.AND
                and preset.mode is FilterMode.INCLUDE
                and not matched
            ):
                break

        if include_seen == 0:
            include_visible = True
        elif self.combination_mode is FilterCombinationMode.OR:
            include_visible = include_matched > 0
        else:
            include_visible = include_matched == include_seen

        return LiveFilterDecision(
            visible=include_visible and not excluded,
            highlighted=highlighted,
            unavailable_reasons=tuple(unavailable),
        )


def _compile_node(node: Mapping[str, Any], compiler: FilterCompiler) -> _CompiledNode:
    if node["type"] == "group":
        return _CompiledGroup(
            LogicalOperator(str(node["operator"])),
            tuple(_compile_node(child, compiler) for child in node["children"]),
        )

    field_name = str(node["field"])
    operator_name = str(node["operator"])
    raw_values = tuple(node["values"])

    if operator_name == StaticFilterOperator.CAN_ID_PATTERN.value:
        return _CompiledCondition(
            field_name,
            operator_name,
            can_id_pattern=CanIdPattern.parse(str(raw_values[0])),
        )

    if operator_name in {
        StaticFilterOperator.PAYLOAD_EXACT.value,
        StaticFilterOperator.PAYLOAD_PREFIX.value,
        StaticFilterOperator.PAYLOAD_CONTAINS.value,
    }:
        operator = StaticFilterOperator(operator_name)
        mode = {
            StaticFilterOperator.PAYLOAD_EXACT: PayloadMatchMode.EXACT,
            StaticFilterOperator.PAYLOAD_PREFIX: PayloadMatchMode.PREFIX,
            StaticFilterOperator.PAYLOAD_CONTAINS: PayloadMatchMode.CONTAINS,
        }[operator]
        return _CompiledCondition(
            field_name,
            operator_name,
            payload_pattern=PayloadPattern.parse(str(raw_values[0]), mode=mode),
        )

    if field_name in _STATIC_FIELD_NAMES:
        operator = StaticFilterOperator(operator_name)
        if field_name == StaticFilterField.CHANNEL.value:
            values = tuple(_parse_int(value) for value in raw_values)
        elif field_name in {
            StaticFilterField.RTR.value,
            StaticFilterField.ERROR_FRAME.value,
        }:
            values = tuple(_parse_bool(value) for value in raw_values)
        else:
            raise ValueError("payload requires a payload matching operator")
        return _CompiledCondition(
            field_name,
            operator_name,
            static_operator=operator,
            values=values,
            membership=(
                frozenset(values)
                if operator in {StaticFilterOperator.IN, StaticFilterOperator.NOT_IN}
                else None
            ),
        )

    legacy_field = _parse_legacy_field(field_name)
    legacy_operator = FilterOperator(operator_name)
    values = tuple(compiler._normalize_value(legacy_field, value) for value in raw_values)
    return _CompiledCondition(
        field_name,
        operator_name,
        legacy_field=legacy_field,
        legacy_operator=legacy_operator,
        values=values,
        membership=(
            frozenset(values)
            if legacy_operator in {FilterOperator.IN, FilterOperator.NOT_IN}
            else None
        ),
    )


def _evaluate_raw(node: _CompiledNode, record: StaticCanFrameRecord | None) -> MatchState:
    if record is None:
        return MatchState.UNAVAILABLE
    if isinstance(node, _CompiledCondition):
        available, actual = _resolve_raw(node.field_name, record)
        if not available:
            return MatchState.UNAVAILABLE
        return _match_state(node, actual, compiler=None)
    return _evaluate_group(node, lambda child: _evaluate_raw(child, record))


def _evaluate_context(
    node: _CompiledNode,
    context: StaticFilterContext | None,
    compiler: FilterCompiler,
) -> MatchState:
    if context is None:
        return MatchState.UNAVAILABLE
    if isinstance(node, _CompiledCondition):
        if node.raw_only:
            return MatchState.UNAVAILABLE
        available, actual = context.resolve(node.field_name)
        if not available:
            return MatchState.UNAVAILABLE
        return _match_state(node, actual, compiler=compiler)
    return _evaluate_group(
        node,
        lambda child: _evaluate_context(child, context, compiler),
    )


def _evaluate_group(node: _CompiledGroup, evaluate_child) -> MatchState:
    if node.operator is LogicalOperator.NOT:
        child = evaluate_child(node.children[0])
        if child is MatchState.UNAVAILABLE:
            return child
        return MatchState.NO_MATCH if child is MatchState.MATCH else MatchState.MATCH

    unavailable = False
    if node.operator is LogicalOperator.AND:
        for child in node.children:
            state = evaluate_child(child)
            if state is MatchState.NO_MATCH:
                return MatchState.NO_MATCH
            unavailable = unavailable or state is MatchState.UNAVAILABLE
        return MatchState.UNAVAILABLE if unavailable else MatchState.MATCH

    for child in node.children:
        state = evaluate_child(child)
        if state is MatchState.MATCH:
            return MatchState.MATCH
        unavailable = unavailable or state is MatchState.UNAVAILABLE
    return MatchState.UNAVAILABLE if unavailable else MatchState.NO_MATCH


def _match_state(
    condition: _CompiledCondition,
    actual: Any,
    *,
    compiler: FilterCompiler | None,
) -> MatchState:
    try:
        if condition.can_id_pattern is not None:
            matched = condition.can_id_pattern.matches(int(actual))
        elif condition.payload_pattern is not None:
            matched = condition.payload_pattern.matches(bytes(actual))
        elif condition.static_operator is not None:
            normalized = (
                _parse_int(actual)
                if condition.field_name == StaticFilterField.CHANNEL.value
                else _parse_bool(actual)
            )
            matched = _compare(normalized, condition.static_operator.value, condition)
        else:
            assert condition.legacy_field is not None
            assert condition.legacy_operator is not None
            normalized = (
                compiler._normalize_value(condition.legacy_field, actual)
                if compiler is not None
                else actual
            )
            matched = _compare(normalized, condition.legacy_operator.value, condition)
    except (TypeError, ValueError):
        return MatchState.UNAVAILABLE
    return MatchState.MATCH if matched else MatchState.NO_MATCH


def _resolve_raw(field_name: str, record: StaticCanFrameRecord) -> tuple[bool, Any]:
    if field_name == FilterField.CAN_ID.value:
        return True, record.can_id
    if field_name == FilterField.FRAME_FORMAT.value:
        return True, "ext" if record.extended else "std"
    if field_name == FilterField.DLC.value:
        return True, record.dlc
    if field_name == FilterField.RELATIVE_TIME_US.value:
        return True, record.relative_time_us
    if field_name == StaticFilterField.CHANNEL.value:
        return True, record.channel
    if field_name == StaticFilterField.RTR.value:
        return True, record.rtr
    if field_name == StaticFilterField.ERROR_FRAME.value:
        return True, record.error_frame
    if field_name == StaticFilterField.PAYLOAD.value:
        return True, record.payload
    return False, None


def _compare(actual: Any, operator: str, condition: _CompiledCondition) -> bool:
    values = condition.values
    if operator == "eq":
        return actual == values[0]
    if operator == "ne":
        return actual != values[0]
    if operator == "gt":
        return actual > values[0]
    if operator == "ge":
        return actual >= values[0]
    if operator == "lt":
        return actual < values[0]
    if operator == "le":
        return actual <= values[0]
    if operator == "between":
        return values[0] <= actual <= values[1]
    if operator == "outside":
        return actual < values[0] or actual > values[1]
    if operator == "in":
        return actual in condition.membership
    if operator == "not_in":
        return actual not in condition.membership
    raise ValueError(f"unsupported operator: {operator}")


def _parse_legacy_field(value: str) -> FilterFieldName:
    try:
        return FilterField(value)
    except ValueError:
        return ProtocolFilterField(value)


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


def _tree_uses_any_field(node: object, fields: frozenset[str]) -> bool:
    if not isinstance(node, dict):
        return False
    if node.get("type") == "condition":
        return str(node.get("field", "")) in fields
    children = node.get("children", ())
    if not isinstance(children, (list, tuple)):
        return False
    return any(_tree_uses_any_field(child, fields) for child in children)
