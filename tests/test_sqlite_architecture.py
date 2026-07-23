from __future__ import annotations

import sqlite3
import sys

import pytest

from app.project import CrtProject
from app.project_search_index import ProjectSearchIndex
from app.sqlite_connection import ClosingSqliteConnection


def test_sqlite_policy_is_declared_without_package_monkey_patch(tmp_path) -> None:
    assert "app.sqlite_lifecycle" not in sys.modules
    assert CrtProject._connect.__module__ == "app.project"
    assert ProjectSearchIndex.is_current.__module__ == "app.project_search_index"
    assert ProjectSearchIndex._begin_or_resume.__module__ == "app.project_search_index"

    project = CrtProject.create(tmp_path / "project", name="SQLite architecture")
    repository = ProjectSearchIndex(project)

    project_connection = project._connect()
    assert isinstance(project_connection, ClosingSqliteConnection)
    with project_connection as connection:
        connection.execute("SELECT 1").fetchone()
    with pytest.raises(sqlite3.ProgrammingError):
        project_connection.execute("SELECT 1")

    search_connection = repository._connect()
    assert isinstance(search_connection, ClosingSqliteConnection)
    with search_connection as connection:
        connection.execute("SELECT 1").fetchone()
    with pytest.raises(sqlite3.ProgrammingError):
        search_connection.execute("SELECT 1")
