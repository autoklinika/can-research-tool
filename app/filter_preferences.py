from __future__ import annotations

import sqlite3
from enum import StrEnum
from pathlib import Path


class FilterCombinationMode(StrEnum):
    """Project-wide combination rule for active Include presets."""

    AND = "and"
    OR = "or"


class ProjectFilterPreferences:
    """Persist small Global Filter Engine preferences in the project database."""

    _COMBINATION_KEY = "include_combination_mode"

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS filter_settings(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    modified_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def combination_mode(self) -> FilterCombinationMode:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM filter_settings WHERE key = ?",
                (self._COMBINATION_KEY,),
            ).fetchone()
        if row is None:
            return FilterCombinationMode.AND
        try:
            return FilterCombinationMode(str(row[0]))
        except ValueError:
            return FilterCombinationMode.AND

    def set_combination_mode(self, mode: FilterCombinationMode | str) -> None:
        normalized = FilterCombinationMode(str(mode))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO filter_settings(key, value, modified_at_utc)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    modified_at_utc = CURRENT_TIMESTAMP
                """,
                (self._COMBINATION_KEY, normalized.value),
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
