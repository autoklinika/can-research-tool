from __future__ import annotations

import sqlite3
from os import PathLike
from typing import Any


Connection = sqlite3.Connection


class ClosingSqliteConnection(sqlite3.Connection):
    """SQLite connection whose context manager also closes the file handle.

    Python's standard ``sqlite3.Connection`` commits or rolls back on context
    exit but does not close the connection. CRT uses short-lived connections, so
    releasing the handle at the same boundary is the intended contract and is
    required for deterministic cleanup on Windows.
    """

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()


def connect(
    database: str | bytes | PathLike[str] | PathLike[bytes],
    *args: Any,
    **kwargs: Any,
) -> ClosingSqliteConnection:
    """Open a context-managed SQLite connection with deterministic close."""

    kwargs.setdefault("factory", ClosingSqliteConnection)
    return sqlite3.connect(database, *args, **kwargs)
