from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QWidget

from app.filters import FilterPreset
from app.project import CrtProject


@dataclass(slots=True)
class FilterShortcutCheck:
    canonical_by_id: dict[str, str] = field(default_factory=dict)
    errors_by_id: dict[str, list[str]] = field(default_factory=dict)

    @property
    def messages(self) -> tuple[str, ...]:
        messages: list[str] = []
        for preset_id in sorted(self.errors_by_id):
            messages.extend(self.errors_by_id[preset_id])
        return tuple(messages)

    def add_error(self, preset: FilterPreset, message: str) -> None:
        self.errors_by_id.setdefault(preset.id, []).append(message)


def canonical_shortcut(text: str) -> str:
    raw = str(text).strip()
    if not raw:
        return ""
    sequence = QKeySequence.fromString(raw, QKeySequence.PortableText)
    if sequence.isEmpty():
        return ""
    return sequence.toString(QKeySequence.PortableText)


def check_filter_shortcuts(
    presets: Iterable[FilterPreset],
    *,
    project: CrtProject,
    action_root: QWidget | None,
) -> FilterShortcutCheck:
    """Validate syntax, duplicates and conflicts with markers/application actions."""

    normalized = list(presets)
    result = FilterShortcutCheck()
    by_sequence: dict[str, list[FilterPreset]] = {}

    for preset in normalized:
        raw = preset.shortcut.strip()
        if not raw:
            continue
        canonical = canonical_shortcut(raw)
        if not canonical:
            result.add_error(preset, f"Preset „{preset.name}”: nieprawidłowy skrót „{raw}”.")
            continue
        result.canonical_by_id[preset.id] = canonical
        by_sequence.setdefault(canonical.casefold(), []).append(preset)

    for sequence, owners in by_sequence.items():
        if len(owners) < 2:
            continue
        names = ", ".join(f"„{preset.name}”" for preset in owners)
        for preset in owners:
            result.add_error(
                preset,
                f"Skrót {result.canonical_by_id[preset.id]} jest przypisany do kilku presetów: {names}.",
            )

    marker_shortcuts: dict[str, str] = {}
    for marker in project.list_marker_presets():
        if not marker.enabled:
            continue
        canonical = canonical_shortcut(marker.shortcut)
        if canonical:
            marker_shortcuts[canonical.casefold()] = marker.name

    action_shortcuts: dict[str, str] = {}
    if action_root is not None:
        for action in action_root.findChildren(QAction):
            sequences = list(action.shortcuts())
            if not sequences and not action.shortcut().isEmpty():
                sequences = [action.shortcut()]
            for sequence in sequences:
                canonical = sequence.toString(QKeySequence.PortableText)
                if canonical:
                    action_shortcuts[canonical.casefold()] = action.text() or action.objectName()

    for preset in normalized:
        canonical = result.canonical_by_id.get(preset.id)
        if not canonical:
            continue
        key = canonical.casefold()
        marker_name = marker_shortcuts.get(key)
        if marker_name:
            result.add_error(
                preset,
                f"Preset „{preset.name}”: skrót {canonical} jest używany przez znacznik „{marker_name}”.",
            )
        action_name = action_shortcuts.get(key)
        if action_name:
            result.add_error(
                preset,
                f"Preset „{preset.name}”: skrót {canonical} jest używany przez akcję aplikacji „{action_name}”.",
            )

    return result
