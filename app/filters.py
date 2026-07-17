from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Iterable, Mapping
from uuid import uuid4

if TYPE_CHECKING:
    from .logical_records import LogicalMessageRecord


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
    """Raw-frame fields currently exposed by the visual filter editor."""

    CAN_ID = "can_id"
    FRAME_FORMAT = "frame_format"
    DLC = "dlc"
    RELATIVE_TIME_US = "relative_time_us"


class ProtocolFilterField(StrEnum):
    """Logical-message fields evaluated by the same global filter compiler.

    They intentionally remain separate from ``FilterField`` until the logical-message
    filter editor is introduced. Existing GUI code iterates ``FilterField`` and must
    continue exposing only fields that can be tested against a raw CAN frame.
    """

    PROTOCOL = "protocol"
    TRANSPORT = "transport"
    MESSAGE_NAME = "message_name"
    COMPLETE = "complete"
    ERROR = "error"
    CONFIDENCE = "confidence"
    SOURCE_FRAME_COUNT = "source_frame_count"
    PGN = "pgn"
    SOURCE_ADDRESS = "source_address"
    DESTINATION_ADDRESS = "destination_address"
    SID = "sid"
    BASE_SID = "base_sid"
    DIRECTION = "direction"
    NRC = "nrc"
    DID = "did"
    ROUTINE_ID = "routine_id"
    SUBFUNCTION = "subfunction"


FilterFieldName = FilterField | ProtocolFilterField
FilterScalar = bool | int | float | str


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
class FilterContext:
    """Typed values available while evaluating one raw frame or logical message."""

    values: Mapping[str, FilterScalar] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    @classmethod
    def from_frame(cls, frame: CanFrameRecord) -> FilterContext:
        return cls(
            {
                FilterField.CAN_ID.value: frame.can_id,
                FilterField.FRAME_FORMAT.value: "ext" if frame.extended else "std",
                FilterField.DLC.value: frame.dlc,
                FilterField.RELATIVE_TIME_US.value: frame.relative_time_us,
            }
        )

    @classmethod
    def from_logical_message(
        cls,
        record: LogicalMessageRecord,
        *,
        relative_time_us: int | None = None,
    ) -> FilterContext:
        values: dict[str, FilterScalar] = {
            FilterField.FRAME_FORMAT.value: "ext" if record.is_extended_id else "std",
            ProtocolFilterField.PROTOCOL.value: record.protocol,
            ProtocolFilterField.TRANSPORT.value: record.transport,
            ProtocolFilterField.MESSAGE_NAME.value: record.name,
            ProtocolFilterField.COMPLETE.value: record.complete,
            ProtocolFilterField.ERROR.value: record.error,
            ProtocolFilterField.CONFIDENCE.value: record.confidence,
            ProtocolFilterField.SOURCE_FRAME_COUNT.value: record.frame_count,
        }
        if record.arbitration_id is not None:
            values[FilterField.CAN_ID.value] = record.arbitration_id
        if relative_time_us is not None:
            values[FilterField.RELATIVE_TIME_US.value] = relative_time_us
        if record.pgn is not None:
            values[ProtocolFilterField.PGN.value] = record.pgn
        if record.source_address is not None:
            values[ProtocolFilterField.SOURCE_ADDRESS.value] = record.source_address
        if record.destination_address is not None:
            values[ProtocolFilterField.DESTINATION_ADDRESS.value] = record.destination_address

        fields = record.fields or {}
        _copy_present(fields, values, "service_id", ProtocolFilterField.SID)
        if fields.get("base_service_id") is not None:
            values[ProtocolFilterField.BASE_SID.value] = fields["base_service_id"]
        elif fields.get("requested_service_id") is not None:
            values[ProtocolFilterField.BASE_SID.value] = fields["requested_service_id"]
        _copy_present(fields, values, "direction", ProtocolFilterField.DIRECTION)
        _copy_present(fields, values, "negative_response_code", ProtocolFilterField.NRC)
        _copy_present(fields, values, "did", ProtocolFilterField.DID)
        _copy_present(fields, values, "routine_id", ProtocolFilterField.ROUTINE_ID)
        _copy_present(fields, values, "subfunction", ProtocolFilterField.SUBFUNCTION)
        return cls(values)

    def resolve(self, field_name: FilterFieldName) -> tuple[bool, FilterScalar | None]:
        key = field_name.value
        if key not in self.values:
            return False, None
        return True, self.values[key]


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
    root: dict[str, Any] = field(
        default_factory=lambda: {"type": "group", "operator": "and", "children": []}
    )
    format_version: int = FILTER_FORMAT_VERSION

    @classmethod
    def create(cls, name: str = "Nowy filtr") -> FilterPreset:
        return cls(id=str(uuid4()), name=name)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> FilterPreset:
        return cls(
            id=str(payload.get("id") or uuid4()),
            name=str(payload.get("name") or "Filtr"),
            description=str(payload.get("description") or ""),
            enabled=bool(payload.get("enabled", True)),
            mode=FilterMode(str(payload.get("mode", FilterMode.INCLUDE.value))),
            shortcut=str(payload.get("shortcut") or ""),
            scope=[str(item) for item in payload.get("scope", ["live", "stored_session"])],
            root=dict(
                payload.get("root")
                or {"type": "group", "operator": "and", "children": []}
            ),
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
            issues.append(
                ValidationIssue(
                    "preset.format_version",
                    "Nieobsługiwana wersja formatu filtra.",
                )
            )
        self._validate_node(preset.root, "root", 0, issues)
        return issues

    def evaluate(
        self,
        preset: FilterPreset,
        record: CanFrameRecord | FilterContext,
    ) -> FilterResult:
        context = record if isinstance(record, FilterContext) else FilterContext.from_frame(record)
        return self.evaluate_context(preset, context)

    def evaluate_context(self, preset: FilterPreset, context: FilterContext) -> FilterResult:
        issues = self.validate(preset)
        if issues:
            return FilterResult(MatchState.UNAVAILABLE, issues[0].message)
        return self._evaluate_node(preset.root, context)

    def evaluate_logical_message(
        self,
        preset: FilterPreset,
        record: LogicalMessageRecord,
        *,
        relative_time_us: int | None = None,
    ) -> FilterResult:
        return self.evaluate_context(
            preset,
            FilterContext.from_logical_message(record, relative_time_us=relative_time_us),
        )

    def _validate_node(
        self,
        node: Mapping[str, Any],
        path: str,
        depth: int,
        issues: list[ValidationIssue],
    ) -> None:
        if depth > self.max_depth:
            issues.append(
                ValidationIssue(path, f"Maksymalna głębokość filtra to {self.max_depth}.")
            )
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
                issues.append(
                    ValidationIssue(path, "Grupa NOT musi zawierać dokładnie jeden element.")
                )
            if operator in {LogicalOperator.AND, LogicalOperator.OR} and not children:
                issues.append(ValidationIssue(path, "Grupa logiczna nie może być pusta."))
            for index, child in enumerate(children):
                if not isinstance(child, Mapping):
                    issues.append(
                        ValidationIssue(
                            f"{path}.children[{index}]",
                            "Węzeł musi być obiektem.",
                        )
                    )
                else:
                    self._validate_node(
                        child,
                        f"{path}.children[{index}]",
                        depth + 1,
                        issues,
                    )
            return
        if node_type != "condition":
            issues.append(ValidationIssue(path, "Węzeł musi mieć typ group albo condition."))
            return
        try:
            field_name = _parse_filter_field(str(node.get("field", "")))
            operator = FilterOperator(str(node.get("operator", "")))
        except ValueError:
            issues.append(ValidationIssue(path, "Nieznane pole lub operator warunku."))
            return
        values = node.get("values")
        if not isinstance(values, list):
            issues.append(ValidationIssue(path, "Pole values musi być listą."))
            return
        required = 2 if operator in {FilterOperator.BETWEEN, FilterOperator.OUTSIDE} else 1
        if len(values) < required:
            issues.append(
                ValidationIssue(path, "Warunek nie zawiera wymaganej liczby wartości.")
            )
            return
        try:
            normalized = [self._normalize_value(field_name, value) for value in values]
        except (TypeError, ValueError) as exc:
            issues.append(ValidationIssue(path, f"Nieprawidłowa wartość: {exc}"))
            return
        self._validate_bounds(field_name, normalized, path, issues)

    @staticmethod
    def _validate_bounds(
        field_name: FilterFieldName,
        values: list[FilterScalar],
        path: str,
        issues: list[ValidationIssue],
    ) -> None:
        limits: dict[FilterFieldName, tuple[float, float, str]] = {
            FilterField.CAN_ID: (
                0,
                0x1FFFFFFF,
                "CAN ID musi należeć do zakresu 0x0–0x1FFFFFFF.",
            ),
            FilterField.DLC: (0, 64, "DLC musi należeć do zakresu 0–64."),
            FilterField.RELATIVE_TIME_US: (
                0,
                float("inf"),
                "Czas względny nie może być ujemny.",
            ),
            ProtocolFilterField.CONFIDENCE: (
                0,
                1,
                "Pewność klasyfikacji musi należeć do zakresu 0–1.",
            ),
            ProtocolFilterField.SOURCE_FRAME_COUNT: (
                0,
                float("inf"),
                "Liczba ramek źródłowych nie może być ujemna.",
            ),
            ProtocolFilterField.PGN: (
                0,
                0x3FFFF,
                "PGN musi należeć do zakresu 0x0–0x3FFFF.",
            ),
            ProtocolFilterField.SOURCE_ADDRESS: (
                0,
                0xFF,
                "Source Address musi należeć do zakresu 0x00–0xFF.",
            ),
            ProtocolFilterField.DESTINATION_ADDRESS: (
                0,
                0xFF,
                "Destination Address musi należeć do zakresu 0x00–0xFF.",
            ),
            ProtocolFilterField.SID: (
                0,
                0xFF,
                "SID musi należeć do zakresu 0x00–0xFF.",
            ),
            ProtocolFilterField.BASE_SID: (
                0,
                0xFF,
                "Bazowy SID musi należeć do zakresu 0x00–0xFF.",
            ),
            ProtocolFilterField.NRC: (
                0,
                0xFF,
                "NRC musi należeć do zakresu 0x00–0xFF.",
            ),
            ProtocolFilterField.SUBFUNCTION: (
                0,
                0xFF,
                "Subfunction musi należeć do zakresu 0x00–0xFF.",
            ),
            ProtocolFilterField.DID: (
                0,
                0xFFFF,
                "DID musi należeć do zakresu 0x0000–0xFFFF.",
            ),
            ProtocolFilterField.ROUTINE_ID: (
                0,
                0xFFFF,
                "Routine ID musi należeć do zakresu 0x0000–0xFFFF.",
            ),
        }
        limit = limits.get(field_name)
        if limit is None:
            return
        minimum, maximum, message = limit
        if any(not minimum <= float(value) <= maximum for value in values):
            issues.append(ValidationIssue(path, message))

    def _evaluate_node(
        self,
        node: Mapping[str, Any],
        context: FilterContext,
    ) -> FilterResult:
        if node["type"] == "condition":
            return self._evaluate_condition(node, context)
        operator = LogicalOperator(node["operator"])
        children = [self._evaluate_node(child, context) for child in node["children"]]
        if operator == LogicalOperator.NOT:
            child = children[0]
            if child.state == MatchState.UNAVAILABLE:
                return child
            return FilterResult(
                MatchState.NO_MATCH if child.state == MatchState.MATCH else MatchState.MATCH
            )
        if operator == LogicalOperator.AND:
            if any(result.state == MatchState.NO_MATCH for result in children):
                return FilterResult(MatchState.NO_MATCH)
            unavailable = next(
                (result for result in children if result.state == MatchState.UNAVAILABLE),
                None,
            )
            return unavailable or FilterResult(MatchState.MATCH)
        if any(result.state == MatchState.MATCH for result in children):
            return FilterResult(MatchState.MATCH)
        unavailable = next(
            (result for result in children if result.state == MatchState.UNAVAILABLE),
            None,
        )
        return unavailable or FilterResult(MatchState.NO_MATCH)

    def _evaluate_condition(
        self,
        node: Mapping[str, Any],
        context: FilterContext,
    ) -> FilterResult:
        field_name = _parse_filter_field(str(node["field"]))
        operator = FilterOperator(node["operator"])
        available, actual = context.resolve(field_name)
        if not available:
            return FilterResult(
                MatchState.UNAVAILABLE,
                f"Pole {field_name.value} nie jest dostępne w tym kontekście.",
            )
        try:
            normalized_actual = self._normalize_value(field_name, actual)
            values = [self._normalize_value(field_name, value) for value in node["values"]]
            match = _compare(normalized_actual, operator, values)
        except (TypeError, ValueError) as exc:
            return FilterResult(
                MatchState.UNAVAILABLE,
                f"Pole {field_name.value} ma nieprawidłową wartość: {exc}",
            )
        return FilterResult(MatchState.MATCH if match else MatchState.NO_MATCH)

    @staticmethod
    def _normalize_value(field_name: FilterFieldName, value: Any) -> FilterScalar:
        if field_name in _TEXT_FIELDS:
            normalized = str(value).strip().casefold()
            if field_name == FilterField.FRAME_FORMAT and normalized not in {"std", "ext"}:
                raise ValueError("format ramki musi mieć wartość std albo ext")
            return normalized
        if field_name in _BOOLEAN_FIELDS:
            return _normalize_bool(value)
        if field_name in _FLOAT_FIELDS:
            return float(value)
        if isinstance(value, str):
            text = value.strip().lower().replace("_", "")
            return int(text, 16) if text.startswith("0x") else int(text, 10)
        return int(value)


_TEXT_FIELDS: frozenset[FilterFieldName] = frozenset(
    {
        FilterField.FRAME_FORMAT,
        ProtocolFilterField.PROTOCOL,
        ProtocolFilterField.TRANSPORT,
        ProtocolFilterField.MESSAGE_NAME,
        ProtocolFilterField.ERROR,
        ProtocolFilterField.DIRECTION,
    }
)
_BOOLEAN_FIELDS: frozenset[FilterFieldName] = frozenset({ProtocolFilterField.COMPLETE})
_FLOAT_FIELDS: frozenset[FilterFieldName] = frozenset({ProtocolFilterField.CONFIDENCE})


def _parse_filter_field(value: str) -> FilterFieldName:
    try:
        return FilterField(value)
    except ValueError:
        return ProtocolFilterField(value)


def _copy_present(
    source: Mapping[str, Any],
    target: dict[str, FilterScalar],
    source_key: str,
    target_field: ProtocolFilterField,
) -> None:
    value = source.get(source_key)
    if value is not None:
        target[target_field.value] = value


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "tak", "complete", "completed"}:
        return True
    if normalized in {"0", "false", "no", "nie", "incomplete"}:
        return False
    raise ValueError("wartość logiczna musi oznaczać tak albo nie")


def _compare(
    actual: FilterScalar,
    operator: FilterOperator,
    values: list[FilterScalar],
) -> bool:
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
        shortcuts = [
            preset.shortcut.strip().lower()
            for preset in normalized
            if preset.enabled and preset.shortcut.strip()
        ]
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
