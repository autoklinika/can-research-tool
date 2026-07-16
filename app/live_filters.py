from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .filters import (
    CanFrameRecord,
    FilterCompiler,
    FilterMode,
    FilterPreset,
    MatchState,
)


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
            preset.mode in {FilterMode.INCLUDE, FilterMode.EXCLUDE}
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

    def decide(self, frame: CanFrameRecord) -> LiveFilterDecision:
        if not self.presets:
            return LiveFilterDecision(True)

        include_results: list[bool] = []
        excluded = False
        highlighted = False
        unavailable: list[str] = []

        for preset in self.presets:
            result = self._compiler.evaluate(preset, frame)
            if result.state is MatchState.UNAVAILABLE:
                unavailable.append(f"{preset.name}: {result.reason or 'warunek niedostępny'}")
                matched = False
            else:
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
