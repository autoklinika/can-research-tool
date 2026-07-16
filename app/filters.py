from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4


FILTER_FORMAT_VERSION = 1


class MatchState(StrEnum):
    MATCH = "match"
    NO_MATCH = "no_match"
    UNAVAILABLE = "unavailable"


class LogicalOperator(StrEnum):
    AND = "and"
    OR = "or"
    NOT = "not"


class FilterMode(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    HIGHLIGHT = "highlight"


class FilterField(StrEnum):
    CAN_ID = "can_id"
    FRAME_FORMAT = "frame_format"
    DLC = "dlc"
    RELATIVE_TIME_US = "relative_time_us"


class FilterOperator(StrEnum):
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


@dataclass(frozen=True, slots=True)
class CanFrameRecord:
    can_id: int
    extended: bool
    dlc: int
    relative_time_us: int = 0
    channel: int = 0


@dataclass(frozen=True, slots=True)
class FilterResult:
    state: MatchState
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    path: str
    message: str


@dataclass(slots=True)
class FilterPreset:
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    mode: FilterMode = FilterMode.INCLUDE
    shortcut: str = ""
    scope: list[str] = field(default_factory=lambda: ["live", "stored_session"])
    root: dict[str, Any] = field(default_factory=lambda: {"type": "group", "operator": "and", "children": []})
    format_version: int = FILTER_FORMAT_VERSION

    @classmethod
    def create(cls, name: str = "Nowy filtr") -> "FilterPreset":
        return cls(id=str(uuid4()), name=name)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FilterPreset":
        return cls(
            id=str(payload.get("id") or uuid4()),
            name=str(payload.get("name") or "Filtr"),
            description=str(payload.get("description") or ""),
            enabled=bool(payload.get("enabled", True)),
            mode=FilterMode(str(payload.get("mode", FilterMode.INCLUDE.value))),
            shortcut=str(payload.get("shortcut") or ""),
            scope=[str(item) for item in payload.get("scope", ["live", "stored_session"])],
            root=dict(payload.get("root") or {"type": "group", "operator": "and", "children": []}),
            format_version=int(payload.get("format_version", FILTER_FORMAT_VERSION)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "mode": self.mode.value,
            "shortcut": self.shortcut,
            "scope": list(self.scope),
            "root": self.root,
        }


class FilterCompiler:
    def __init__(self, max_depth: int = 12) -> None:
        self.max_depth = max_depth

    def validate(self, preset: FilterPreset) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not preset.name.strip():
            issues.append(ValidationIssue("preset.name", "Nazwa filtra nie może być pusta."))
        if preset.format_version != FILTER_FORMAT_VERSION:
            issues.append(ValidationIssue("preset.format_version", "Nieobsługiwana wersja formatu filtra."))
        self._validate_node(preset.root, "root", 0, issues)
        return issues

    def evaluate(self, preset: FilterPreset, frame: CanFrameRecord) -> FilterResult:
        issues = self.validate(preset)
        if issues:
            return FilterResult(MatchState.UNAVAILABLE, issues[0].message)
        return self._evaluate_node(preset.root, frame)

    def _validate_node(
        self,
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
                    self._validate_node(child, f"{path}.children[{index}]", depth + 1, issues)
            return
        if node_type != "condition":
            issues.append(ValidationIssue(path, "Węzeł musi mieć typ group albo condition."))
            return
        try:
            field_name = FilterField(str(node.get("field", "")))
            operator = FilterOperator(str(node.get("operator", "")))
        except ValueError:
            issues.append(ValidationIssue(path, "Nieznane pole lub operator warunku."))
            return
        values = node.get("values")
        if not isinstance(values, list):
            issues.append(ValidationIssue(path, "Pole values musi być listą."))
            return
        required = 2 if operator in {FilterOperator.BETWEEN, FilterOperator.OUTSIDE} else 1
        if operator in {FilterOperator.IN, FilterOperator.NOT_IN}:
            required = 1
        if len(values) < required:
            issues.append(ValidationIssue(path, "Warunek nie zawiera wymaganej liczby wartości."))
            return
        try:
            normalized = [self._normalize_value(field_name, value) for value in values]
        except (TypeError, ValueError) as exc:
            issues.append(ValidationIssue(path, f"Nieprawidłowa wartość: {exc}"))
            return
        if field_name == FilterField.CAN_ID and any(not 0 <= int(value) <= 0x1FFFFFFF for value in normalized):
            issues.append(ValidationIssue(path, "CAN ID musi należeć do zakresu 0x0–0x1FFFFFFF."))
        if field_name == FilterField.DLC and any(not 0 <= int(value) <= 64 for value in normalized):
            issues.append(ValidationIssue(path, "DLC musi należeć do zakresu 0–64."))

    def _evaluate_node(self, node: Mapping[str, Any], frame: CanFrameRecord) -> FilterResult:
        if node["type"] == "condition":
            return self._evaluate_condition(node, frame)
        operator = LogicalOperator(node["operator"])
        children = [self._evaluate_node(child, frame) for child in node["children"]]
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

    def _evaluate_condition(self, node: Mapping[str, Any], frame: CanFrameRecord) -> FilterResult:
        field_name = FilterField(node["field"])
        operator = FilterOperator(node["operator"])
        actual: int | str
        if field_name == FilterField.CAN_ID:
            actual = frame.can_id
        elif field_name == FilterField.FRAME_FORMAT:
            actual = "ext" if frame.extended else "std"
        elif field_name == FilterField.DLC:
            actual = frame.dlc
        elif field_name == FilterField.RELATIVE_TIME_US:
            actual = frame.relative_time_us
        else:
            return FilterResult(MatchState.UNAVAILABLE, f"Pole {field_name} nie jest dostępne.")
        values = [self._normalize_value(field_name, value) for value in node["values"]]
        match = _compare(actual, operator, values)
        return FilterResult(MatchState.MATCH if match else MatchState.NO_MATCH)

    @staticmethod
    def _normalize_value(field_name: FilterField, value: Any) -> int | str:
        if field_name == FilterField.FRAME_FORMAT:
            normalized = str(value).strip().lower()
            if normalized not in {"std", "ext"}:
                raise ValueError("format ramki musi mieć wartość std albo ext")
            return normalized
        if isinstance(value, str):
            text = value.strip().lower().replace("_", "")
            return int(text, 16) if text.startswith("0x") else int(text, 10)
        return int(value)


def _compare(actual: int | str, operator: FilterOperator, values: list[int | str]) -> bool:
    if operator == FilterOperator.EQ:
        return actual == values[0]
    if operator == FilterOperator.NE:
        return actual != values[0]
    if operator == FilterOperator.GT:
        return actual > values[0]
    if operator == FilterOperator.GE:
        return actual >= values[0]
    if operator == FilterOperator.LT:
        return actual < values[0]
    if operator == FilterOperator.LE:
        return actual <= values[0]
    if operator == FilterOperator.BETWEEN:
        return values[0] <= actual <= values[1]
    if operator == FilterOperator.OUTSIDE:
        return actual < values[0] or actual > values[1]
    if operator == FilterOperator.IN:
        return actual in values
    if operator == FilterOperator.NOT_IN:
        return actual not in values
    raise ValueError(f"unsupported operator: {operator}")


class ProjectFilterRepository:
    """Stores versioned filter presets in the project's SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS filter_presets(
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    mode TEXT NOT NULL DEFAULT 'include',
                    shortcut TEXT NOT NULL DEFAULT '',
                    scope_json TEXT NOT NULL,
                    tree_json TEXT NOT NULL,
                    format_version INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    modified_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_filter_shortcut_active
                    ON filter_presets(lower(shortcut))
                    WHERE enabled = 1 AND shortcut <> '';
                """
            )
            connection.commit()

    def list_presets(self) -> list[FilterPreset]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, description, enabled, mode, shortcut,
                       scope_json, tree_json, format_version
                FROM filter_presets
                ORDER BY sort_order, name COLLATE NOCASE
                """
            ).fetchall()
        return [
            FilterPreset(
                id=str(row[0]),
                name=str(row[1]),
                description=str(row[2]),
                enabled=bool(row[3]),
                mode=FilterMode(str(row[4])),
                shortcut=str(row[5]),
                scope=list(json.loads(row[6])),
                root=dict(json.loads(row[7])),
                format_version=int(row[8]),
            )
            for row in rows
        ]

    def save_presets(self, presets: Iterable[FilterPreset]) -> None:
        normalized = list(presets)
        shortcuts = [preset.shortcut.strip().lower() for preset in normalized if preset.enabled and preset.shortcut.strip()]
        if len(shortcuts) != len(set(shortcuts)):
            raise ValueError("Aktywne skróty filtrów muszą być unikalne.")
        with self._connect() as connection:
            connection.execute("DELETE FROM filter_presets")
            connection.executemany(
                """
                INSERT INTO filter_presets(
                    id, name, description, enabled, mode, shortcut,
                    scope_json, tree_json, format_version, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        preset.id,
                        preset.name,
                        preset.description,
                        int(preset.enabled),
                        preset.mode.value,
                        preset.shortcut.strip(),
                        json.dumps(preset.scope, ensure_ascii=False),
                        json.dumps(preset.root, ensure_ascii=False),
                        preset.format_version,
                        index,
                    )
                    for index, preset in enumerate(normalized)
                ],
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
