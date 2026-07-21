from __future__ import annotations

import sqlite3
from types import ModuleType
from typing import Any


class ClosingSqliteConnection(sqlite3.Connection):
    """SQLite connection whose context manager also releases the file handle.

    ``sqlite3.Connection.__exit__`` commits or rolls back a transaction but does
    not close the connection. That distinction is mostly invisible on POSIX,
    where an open database file can still be unlinked, but it leaves CRT SQLite
    files locked on Windows until garbage collection eventually runs.
    """

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()


class ClosingSqliteModule:
    """Module proxy applying ``ClosingSqliteConnection`` to one consumer."""

    def __init__(self, module: ModuleType = sqlite3) -> None:
        self._module = module

    def connect(self, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        kwargs.setdefault("factory", ClosingSqliteConnection)
        return self._module.connect(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._module, name)


def install_project_search_index_sqlite_lifecycle() -> None:
    """Close context-managed CRT project and search-index connections.

    The patch is intentionally scoped to the two application modules that use
    ``with sqlite3.connect(...)`` semantics. Other SQLite consumers that already
    own explicit ``try/finally: connection.close()`` lifecycles are untouched.

    The historical function name is retained to avoid changing package startup
    imports while broadening the fix to the main ``project.sqlite`` repository.
    """

    from . import project, project_search_index

    for consumer in (project, project_search_index):
        if isinstance(consumer.sqlite3, ClosingSqliteModule):
            continue
        consumer.sqlite3 = ClosingSqliteModule(consumer.sqlite3)
