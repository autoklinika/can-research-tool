from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from .filters import (
    CanFrameRecord,
    FilterCompiler,
    FilterContext,
    FilterField,
    FilterMode,
    FilterPreset,
    MatchState,
)

if TYPE_CHECKING:
    from .logical_records import LogicalMessageRecord


@dataclass(frozen=True, slots=True)
class LiveFilterDecision:
    visible: bool
    highlighted: bool = False
    unavailable_reasons: tuple[str, ...] = ()


class ActiveFilterSet:
    """Compiled project presets used only by GUI views.

    Session recording is intentionally outside this class. Include and exclude
    presets control visibility; highlight presets only annotate matching rows.
    Multiple include presets are combined with AND, matching the CRT default.

    ``scope`` prevents a preset intended for a stored session from accidentally
    affecting Live Capture (and vice versa). Passing ``None`` keeps the legacy
    behaviour and is useful for isolated engine tests.

    A preset that is wholly unavailable in the evaluated context is neutral for
    presentation. This allows one project filter set to be shared by raw-frame and
    logical-message tables without a protocol-only condition blanking the raw view,
    or a raw-only condition blanking the logical-message view. The compiler still
    reports ``UNAVAILABLE`` and the reason remains available on the decision.
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
        self.validation_issues = tuple(
            (preset.name, tuple(issues))
            for preset in self.presets
            if (issues := compiler.validate(preset))
        )

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
        """Whether any visibility preset can change the raw-frame table.

        Protocol-only conditions are deliberately neutral for raw frames. Detecting
        that case before scheduling a 250k-row scan avoids wasting CPU and contending
        with the GUI thread for the Python GIL when the user only wants UDS/J1939/
        ISO-TP filtering in the logical-message table.
        """

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
        context = record if isinstance(record, FilterContext) else FilterContext.from_frame(record)
        return self.decide_context(context)

    def decide_logical_message(
        self,
        record: LogicalMessageRecord,
        *,
        relative_time_us: int | None = None,
    ) -> LiveFilterDecision:
        return self.decide_context(
            FilterContext.from_logical_message(record, relative_time_us=relative_time_us)
        )

    def decide_context(self, context: FilterContext) -> LiveFilterDecision:
        if not self.presets:
            return LiveFilterDecision(True)

        include_results: list[bool] = []
        excluded = False
        highlighted = False
        unavailable: list[str] = []

        for preset in self.presets:
            result = self._compiler.evaluate_context(preset, context)
            if result.state is MatchState.UNAVAILABLE:
                unavailable.append(f"{preset.name}: {result.reason or 'warunek niedostępny'}")
                continue

            matched = result.state is MatchState.MATCH
            if preset.mode is FilterMode.INCLUDE:
                include_results.append(matched)
            elif preset.mode is FilterMode.EXCLUDE:
                excluded = excluded or matched
            elif preset.mode is FilterMode.HIGHLIGHT:
                highlighted = highlighted or matched

        include_ok = all(include_results) if include_results else True
        return LiveFilterDecision(
            visible=include_ok and not excluded,
            highlighted=highlighted,
            unavailable_reasons=tuple(unavailable),
        )


def _tree_uses_any_field(node: object, fields: set[str]) -> bool:
    if not isinstance(node, dict):
        return False
    if node.get("type") == "condition":
        return str(node.get("field", "")) in fields
    children = node.get("children", ())
    if not isinstance(children, (list, tuple)):
        return False
    return any(_tree_uses_any_field(child, fields) for child in children)
