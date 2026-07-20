from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable

from .filters import (
    CanFrameRecord,
    FilterCompiler,
    FilterContext,
    FilterField,
    FilterFieldName,
    FilterMode,
    FilterOperator,
    FilterPreset,
    FilterScalar,
    LogicalOperator,
    MatchState,
    ProtocolFilterField,
)

if TYPE_CHECKING:
    from .logical_records import LogicalMessageRecord


@dataclass(frozen=True, slots=True)
class LiveFilterDecision:
    visible: bool
    highlighted: bool = False
    unavailable_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _CompiledCondition:
    field: FilterFieldName
    operator: FilterOperator
    values: tuple[FilterScalar, ...]
    membership: frozenset[FilterScalar] | None = None


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


class ActiveFilterSet:
    """Compiled project presets used only by GUI views.

    Presets are validated and normalized once when the active set is created. The hot
    path never revalidates trees or reparses hexadecimal values for every frame.
    Session recording remains intentionally outside this class.
    """

    def __init__(
        self,
        presets: Iterable[FilterPreset],
        *,
        scope: str | None = None,
    ) -> None:
        compiler = FilterCompiler()
        self.scope = scope
        self.presets = tuple(
            preset
            for preset in presets
            if preset.enabled and (scope is None or scope in preset.scope)
        )
        self._compiler = compiler

        compiled: list[_CompiledPreset] = []
        validation_issues: list[tuple[str, tuple[Any, ...]]] = []
        for preset in self.presets:
            issues = tuple(compiler.validate(preset))
            if issues:
                validation_issues.append((preset.name, issues))
                compiled.append(
                    _CompiledPreset(
                        preset=preset,
                        root=None,
                        validation_error=issues[0].message,
                    )
                )
                continue
            compiled.append(
                _CompiledPreset(
                    preset=preset,
                    root=_compile_node(preset.root, compiler),
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
            preset.mode in {FilterMode.INCLUDE, FilterMode.EXCLUDE} for preset in self.presets
        )

    @property
    def affects_raw_visibility(self) -> bool:
        """Whether any visibility preset can change the raw-frame table."""

        raw_fields = {field.value for field in FilterField}
        return any(
            preset.mode in {FilterMode.INCLUDE, FilterMode.EXCLUDE}
            and _tree_uses_any_field(preset.root, raw_fields)
            for preset in self.presets
        )

    @property
    def signature(self) -> tuple[object, ...]:
        return (
            self.scope,
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

    def decide(self, record: CanFrameRecord | FilterContext) -> LiveFilterDecision:
        if isinstance(record, CanFrameRecord):
            return self._decide_compiled(record=record)
        return self._decide_compiled(context=record)

    def decide_logical_message(
        self,
        record: LogicalMessageRecord,
        *,
        relative_time_us: int | None = None,
    ) -> LiveFilterDecision:
        return self._decide_compiled(
            context=FilterContext.from_logical_message(
                record,
                relative_time_us=relative_time_us,
            )
        )

    def decide_context(self, context: FilterContext) -> LiveFilterDecision:
        return self._decide_compiled(context=context)

    def _decide_compiled(
        self,
        *,
        record: CanFrameRecord | None = None,
        context: FilterContext | None = None,
    ) -> LiveFilterDecision:
        if not self._compiled_presets:
            return LiveFilterDecision(True)

        include_failed = False
        include_seen = False
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
                _evaluate_raw(compiled.root, record)
                if record is not None
                else _evaluate_context(compiled.root, context, self._compiler)
            )
            if state is MatchState.UNAVAILABLE:
                unavailable.append(f"{preset.name}: warunek niedostępny w tym kontekście")
                continue

            matched = state is MatchState.MATCH
            if preset.mode is FilterMode.INCLUDE:
                include_seen = True
                if not matched:
                    include_failed = True
            elif preset.mode is FilterMode.EXCLUDE:
                if matched:
                    excluded = True
            elif preset.mode is FilterMode.HIGHLIGHT:
                if matched:
                    highlighted = True

            if include_failed or excluded:
                # Visibility can no longer recover. Highlight evaluation is presentation
                # only and does not justify walking the remaining trees on a hidden row.
                break

        return LiveFilterDecision(
            visible=(not include_seen or not include_failed) and not excluded,
            highlighted=highlighted,
            unavailable_reasons=tuple(unavailable),
        )


def _compile_node(node: dict[str, Any], compiler: FilterCompiler) -> _CompiledNode:
    if node["type"] == "condition":
        field = _parse_field(str(node["field"]))
        operator = FilterOperator(str(node["operator"]))
        values = tuple(compiler._normalize_value(field, value) for value in node["values"])
        membership = (
            frozenset(values)
            if operator in {FilterOperator.IN, FilterOperator.NOT_IN}
            else None
        )
        return _CompiledCondition(field, operator, values, membership)
    return _CompiledGroup(
        LogicalOperator(str(node["operator"])),
        tuple(_compile_node(child, compiler) for child in node["children"]),
    )


def _evaluate_raw(node: _CompiledNode, record: CanFrameRecord) -> MatchState:
    if isinstance(node, _CompiledCondition):
        available, actual = _resolve_raw(node.field, record)
        if not available:
            return MatchState.UNAVAILABLE
        try:
            matched = _compare_compiled(actual, node)
        except (TypeError, ValueError):
            return MatchState.UNAVAILABLE
        return MatchState.MATCH if matched else MatchState.NO_MATCH
    return _evaluate_group(node, lambda child: _evaluate_raw(child, record))


def _evaluate_context(
    node: _CompiledNode,
    context: FilterContext | None,
    compiler: FilterCompiler,
) -> MatchState:
    if context is None:
        return MatchState.UNAVAILABLE
    if isinstance(node, _CompiledCondition):
        available, actual = context.resolve(node.field)
        if not available:
            return MatchState.UNAVAILABLE
        try:
            normalized = compiler._normalize_value(node.field, actual)
            matched = _compare_compiled(normalized, node)
        except (TypeError, ValueError):
            return MatchState.UNAVAILABLE
        return MatchState.MATCH if matched else MatchState.NO_MATCH
    return _evaluate_group(
        node,
        lambda child: _evaluate_context(child, context, compiler),
    )


def _evaluate_group(
    node: _CompiledGroup,
    evaluate_child,
) -> MatchState:
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


def _resolve_raw(
    field: FilterFieldName,
    record: CanFrameRecord,
) -> tuple[bool, FilterScalar | None]:
    if field is FilterField.CAN_ID:
        return True, record.can_id
    if field is FilterField.FRAME_FORMAT:
        return True, "ext" if record.extended else "std"
    if field is FilterField.DLC:
        return True, record.dlc
    if field is FilterField.RELATIVE_TIME_US:
        return True, record.relative_time_us
    return False, None


def _compare_compiled(actual: FilterScalar, condition: _CompiledCondition) -> bool:
    operator = condition.operator
    values = condition.values
    if operator is FilterOperator.EQ:
        return actual == values[0]
    if operator is FilterOperator.NE:
        return actual != values[0]
    if operator is FilterOperator.GT:
        return actual > values[0]
    if operator is FilterOperator.GE:
        return actual >= values[0]
    if operator is FilterOperator.LT:
        return actual < values[0]
    if operator is FilterOperator.LE:
        return actual <= values[0]
    if operator is FilterOperator.BETWEEN:
        return values[0] <= actual <= values[1]
    if operator is FilterOperator.OUTSIDE:
        return actual < values[0] or actual > values[1]
    if operator is FilterOperator.IN:
        return actual in condition.membership
    if operator is FilterOperator.NOT_IN:
        return actual not in condition.membership
    raise ValueError(f"unsupported operator: {operator}")


def _parse_field(value: str) -> FilterFieldName:
    try:
        return FilterField(value)
    except ValueError:
        return ProtocolFilterField(value)


def _tree_uses_any_field(node: object, fields: set[str]) -> bool:
    if not isinstance(node, dict):
        return False
    if node.get("type") == "condition":
        return str(node.get("field", "")) in fields
    children = node.get("children", ())
    if not isinstance(children, (list, tuple)):
        return False
    return any(_tree_uses_any_field(child, fields) for child in children)
