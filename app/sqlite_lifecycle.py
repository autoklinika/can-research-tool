from __future__ import annotations

import sqlite3
from types import ModuleType
from typing import Any


class ClosingSqliteConnection(sqlite3.Connection):
    """SQLite connection whose context manager also releases the file handle.

    ``sqlite3.Connection.__exit__`` commits or rolls back a transaction but does
    not close the connection. That distinction is mostly invisible on POSIX,
    where an open database file can still be unlinked, but it leaves project
    cache files locked on Windows until cyclic garbage collection runs.
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
    """Make project-search context-managed connections close deterministically.

    The patch is intentionally scoped to ``app.project_search_index`` instead
    of replacing ``sqlite3.connect`` process-wide. Existing project and logical
    cache repositories therefore retain their current lifecycle contracts.
    """

    from . import project_search_index

    if isinstance(project_search_index.sqlite3, ClosingSqliteModule):
        return
    project_search_index.sqlite3 = ClosingSqliteModule()
