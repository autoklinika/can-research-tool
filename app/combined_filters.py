from __future__ import annotations

from typing import Iterable

from .filter_preferences import FilterCombinationMode
from .filters import CanFrameRecord, FilterContext, FilterMode, FilterPreset, MatchState
from .live_filters import (
    ActiveFilterSet,
    LiveFilterDecision,
    _evaluate_context,
    _evaluate_raw,
)


class CombinedActiveFilterSet(ActiveFilterSet):
    """Active filter set with a project-wide AND/OR rule for Include presets.

    Exclude presets keep their safety-oriented semantics: a match from any Exclude
    preset hides the record. Highlight presets remain presentation-only and never
    influence visibility.
    """

    def __init__(
        self,
        presets: Iterable[FilterPreset],
        *,
        scope: str | None = None,
        combination_mode: FilterCombinationMode | str = FilterCombinationMode.AND,
    ) -> None:
        self.combination_mode = FilterCombinationMode(str(combination_mode))
        super().__init__(presets, scope=scope)

    @property
    def signature(self) -> tuple[object, ...]:
        return (self.combination_mode.value, *super().signature)

    def _decide_compiled(
        self,
        *,
        record: CanFrameRecord | None = None,
        context: FilterContext | None = None,
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
                _evaluate_raw(compiled.root, record)
                if record is not None
                else _evaluate_context(compiled.root, context, self._compiler)
            )
            if state is MatchState.UNAVAILABLE:
                unavailable.append(f"{preset.name}: warunek niedostępny w tym kontekście")
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
                # In AND mode visibility cannot recover after one available Include
                # preset fails. Highlight is presentation-only for visible rows.
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
