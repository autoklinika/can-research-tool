from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from .domain import ComparisonSet
from .project import CrtProject
from .project_domain_store import ProjectDomainStore


class ComparisonSetStore:
    """Manage persistent multi-session sets without changing session data.

    The store reuses the comparison-set tables introduced by the existing
    project-domain migration. It never writes session streams, search indexes or
    capture state.
    """

    def __init__(self, project: CrtProject) -> None:
        self.project = project
        self._domain_store = ProjectDomainStore(project)

    def create(
        self,
        *,
        name: str,
        session_ids: Sequence[str],
        base_session_id: str | None = None,
        synchronization_mode: str = "none",
        parameters: Mapping[str, Any] | None = None,
    ) -> ComparisonSet:
        return self._domain_store.create_comparison_set(
            name=name,
            session_ids=session_ids,
            base_session_id=base_session_id,
            synchronization_mode=synchronization_mode,
            parameters=parameters,
        )

    def list(self) -> list[ComparisonSet]:
        with self.project._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, base_session_id, synchronization_mode,
                       parameters_json, created_at_utc, updated_at_utc
                FROM comparison_sets
                ORDER BY updated_at_utc DESC, name COLLATE NOCASE, id
                """
            ).fetchall()
            return [self._hydrate(connection, row) for row in rows]

    def get(self, comparison_set_id: str) -> ComparisonSet:
        with self.project._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, base_session_id, synchronization_mode,
                       parameters_json, created_at_utc, updated_at_utc
                FROM comparison_sets
                WHERE id = ?
                """,
                (comparison_set_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown comparison set: {comparison_set_id}")
            return self._hydrate(connection, row)

    def update(
        self,
        comparison_set_id: str,
        *,
        name: str,
        session_ids: Sequence[str],
        base_session_id: str | None = None,
        synchronization_mode: str = "none",
        parameters: Mapping[str, Any] | None = None,
    ) -> ComparisonSet:
        current = self.get(comparison_set_id)
        updated = ComparisonSet(
            id=current.id,
            name=name.strip(),
            session_ids=tuple(dict.fromkeys(session_ids)),
            base_session_id=base_session_id,
            synchronization_mode=synchronization_mode.strip(),
            parameters=dict(current.parameters if parameters is None else parameters),
            created_at_utc=current.created_at_utc,
            updated_at_utc=_utc_now(),
        )

        with self.project._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._require_mutable(connection, updated.id)
                self._require_sessions(connection, updated.session_ids)
                connection.execute(
                    """
                    UPDATE comparison_sets
                    SET name = ?, base_session_id = ?, synchronization_mode = ?,
                        parameters_json = ?, updated_at_utc = ?
                    WHERE id = ?
                    """,
                    (
                        updated.name,
                        updated.base_session_id,
                        updated.synchronization_mode,
                        _canonical_json(updated.parameters),
                        updated.updated_at_utc,
                        updated.id,
                    ),
                )
                connection.execute(
                    "DELETE FROM comparison_set_sessions WHERE comparison_set_id = ?",
                    (updated.id,),
                )
                connection.executemany(
                    """
                    INSERT INTO comparison_set_sessions(
                        comparison_set_id, session_id, role, sort_order
                    ) VALUES (?, ?, ?, ?)
                    """,
                    [
                        (
                            updated.id,
                            session_id,
                            "base" if session_id == updated.base_session_id else "compared",
                            sort_order,
                        )
                        for sort_order, session_id in enumerate(updated.session_ids)
                    ],
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return updated

    def delete(self, comparison_set_id: str) -> None:
        with self.project._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if not self._exists(connection, comparison_set_id):
                    raise KeyError(f"unknown comparison set: {comparison_set_id}")
                self._require_mutable(connection, comparison_set_id)
                connection.execute(
                    "DELETE FROM comparison_sets WHERE id = ?",
                    (comparison_set_id,),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def analysis_run_count(self, comparison_set_id: str) -> int:
        with self.project._connect() as connection:
            if not self._exists(connection, comparison_set_id):
                raise KeyError(f"unknown comparison set: {comparison_set_id}")
            return self._analysis_run_count(connection, comparison_set_id)

    def is_locked(self, comparison_set_id: str) -> bool:
        return self.analysis_run_count(comparison_set_id) > 0

    @staticmethod
    def _hydrate(connection: Any, row: tuple[object, ...]) -> ComparisonSet:
        comparison_set_id = str(row[0])
        session_rows = connection.execute(
            """
            SELECT session_id
            FROM comparison_set_sessions
            WHERE comparison_set_id = ?
            ORDER BY sort_order
            """,
            (comparison_set_id,),
        ).fetchall()
        parameters = json.loads(str(row[4]))
        if not isinstance(parameters, dict):
            raise ValueError("comparison set parameters must be a JSON object")
        return ComparisonSet(
            id=comparison_set_id,
            name=str(row[1]),
            session_ids=tuple(str(item[0]) for item in session_rows),
            base_session_id=None if row[2] is None else str(row[2]),
            synchronization_mode=str(row[3]),
            parameters=parameters,
            created_at_utc=str(row[5]),
            updated_at_utc=str(row[6]),
        )

    @staticmethod
    def _require_sessions(connection: Any, session_ids: Sequence[str]) -> None:
        missing = [
            session_id
            for session_id in session_ids
            if connection.execute(
                "SELECT 1 FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            is None
        ]
        if missing:
            raise KeyError(f"unknown sessions: {missing}")

    @staticmethod
    def _exists(connection: Any, comparison_set_id: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM comparison_sets WHERE id = ?",
                (comparison_set_id,),
            ).fetchone()
            is not None
        )

    @classmethod
    def _require_mutable(cls, connection: Any, comparison_set_id: str) -> None:
        if not cls._exists(connection, comparison_set_id):
            raise KeyError(f"unknown comparison set: {comparison_set_id}")
        run_count = cls._analysis_run_count(connection, comparison_set_id)
        if run_count:
            raise ValueError(
                "comparison set is referenced by analysis runs and cannot be modified"
            )

    @staticmethod
    def _analysis_run_count(connection: Any, comparison_set_id: str) -> int:
        row = connection.execute(
            """
            SELECT COUNT(DISTINCT analysis_run_id)
            FROM analysis_inputs
            WHERE input_kind = 'comparison_set' AND input_id = ?
            """,
            (comparison_set_id,),
        ).fetchone()
        return 0 if row is None else int(row[0])


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["ComparisonSetStore"]
