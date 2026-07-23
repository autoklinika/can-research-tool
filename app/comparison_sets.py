from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .domain import ComparisonSet
from .project import CrtProject
from .project_domain_store import ProjectDomainStore


_DELETED_AT_PARAMETER = "_crt_deleted_at_utc"


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
        cleaned_parameters = dict(parameters or {})
        cleaned_parameters.pop(_DELETED_AT_PARAMETER, None)
        return self._domain_store.create_comparison_set(
            name=name,
            session_ids=session_ids,
            base_session_id=base_session_id,
            synchronization_mode=synchronization_mode,
            parameters=cleaned_parameters,
        )

    def list(self, *, include_deleted: bool = False) -> list[ComparisonSet]:
        with self.project._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, base_session_id, synchronization_mode,
                       parameters_json, created_at_utc, updated_at_utc
                FROM comparison_sets
                ORDER BY updated_at_utc DESC, name COLLATE NOCASE, id
                """
            ).fetchall()
            comparison_sets = [self._hydrate(connection, row) for row in rows]
        if include_deleted:
            return comparison_sets
        return [item for item in comparison_sets if not self.is_deleted(item)]

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
        updated_parameters = dict(
            current.parameters if parameters is None else parameters
        )
        updated_parameters.pop(_DELETED_AT_PARAMETER, None)
        updated = ComparisonSet(
            id=current.id,
            name=name.strip(),
            session_ids=tuple(dict.fromkeys(session_ids)),
            base_session_id=base_session_id,
            synchronization_mode=synchronization_mode.strip(),
            parameters=updated_parameters,
            created_at_utc=current.created_at_utc,
            updated_at_utc=_utc_now(),
        )

        with self.project._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._require_mutable(connection, updated.id)
                self._require_sessions(connection, updated.session_ids)
                self._update_definition(connection, updated)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return updated

    def fork(
        self,
        comparison_set_id: str,
        *,
        name: str,
        session_ids: Sequence[str],
        base_session_id: str | None = None,
        synchronization_mode: str = "none",
        parameters: Mapping[str, Any] | None = None,
    ) -> ComparisonSet:
        """Create a replacement for an analysed set and archive the old one.

        Analysis inputs keep referencing the original immutable definition. The
        replacement receives a new identity and becomes the editable active set.
        """

        current = self.get(comparison_set_id)
        replacement_parameters = dict(
            current.parameters if parameters is None else parameters
        )
        replacement_parameters.pop(_DELETED_AT_PARAMETER, None)
        now = _utc_now()
        replacement = ComparisonSet(
            id=str(uuid4()),
            name=name.strip(),
            session_ids=tuple(dict.fromkeys(session_ids)),
            base_session_id=base_session_id,
            synchronization_mode=synchronization_mode.strip(),
            parameters=replacement_parameters,
            created_at_utc=now,
            updated_at_utc=now,
        )

        with self.project._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if not self._exists(connection, current.id):
                    raise KeyError(f"unknown comparison set: {current.id}")
                if self._is_deleted_connection(connection, current.id):
                    raise ValueError("deleted comparison set cannot be revised")
                if not self._analysis_run_count(connection, current.id):
                    raise ValueError(
                        "comparison set has no analysis history and should be updated"
                    )
                self._require_sessions(connection, replacement.session_ids)
                self._insert_definition(connection, replacement)
                self._soft_delete(connection, current, deleted_at_utc=now)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return replacement

    def delete(self, comparison_set_id: str) -> bool:
        """Delete an unused set or archive an analysed set.

        Returns ``True`` when the row was retained as a hidden historical source,
        and ``False`` when an unused definition was physically removed.
        """

        current = self.get(comparison_set_id)
        with self.project._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if not self._exists(connection, comparison_set_id):
                    raise KeyError(f"unknown comparison set: {comparison_set_id}")
                run_count = self._analysis_run_count(connection, comparison_set_id)
                if run_count:
                    self._soft_delete(connection, current)
                    preserved = True
                else:
                    connection.execute(
                        "DELETE FROM comparison_sets WHERE id = ?",
                        (comparison_set_id,),
                    )
                    preserved = False
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return preserved

    def analysis_run_count(self, comparison_set_id: str) -> int:
        with self.project._connect() as connection:
            if not self._exists(connection, comparison_set_id):
                raise KeyError(f"unknown comparison set: {comparison_set_id}")
            return self._analysis_run_count(connection, comparison_set_id)

    def is_locked(self, comparison_set_id: str) -> bool:
        return self.analysis_run_count(comparison_set_id) > 0

    @staticmethod
    def is_deleted(comparison_set: ComparisonSet) -> bool:
        return bool(comparison_set.parameters.get(_DELETED_AT_PARAMETER))

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

    @classmethod
    def _insert_definition(
        cls,
        connection: Any,
        comparison_set: ComparisonSet,
    ) -> None:
        connection.execute(
            """
            INSERT INTO comparison_sets(
                id, name, base_session_id, synchronization_mode,
                parameters_json, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                comparison_set.id,
                comparison_set.name,
                comparison_set.base_session_id,
                comparison_set.synchronization_mode,
                _canonical_json(comparison_set.parameters),
                comparison_set.created_at_utc,
                comparison_set.updated_at_utc,
            ),
        )
        cls._insert_sessions(connection, comparison_set)

    @classmethod
    def _update_definition(
        cls,
        connection: Any,
        comparison_set: ComparisonSet,
    ) -> None:
        connection.execute(
            """
            UPDATE comparison_sets
            SET name = ?, base_session_id = ?, synchronization_mode = ?,
                parameters_json = ?, updated_at_utc = ?
            WHERE id = ?
            """,
            (
                comparison_set.name,
                comparison_set.base_session_id,
                comparison_set.synchronization_mode,
                _canonical_json(comparison_set.parameters),
                comparison_set.updated_at_utc,
                comparison_set.id,
            ),
        )
        connection.execute(
            "DELETE FROM comparison_set_sessions WHERE comparison_set_id = ?",
            (comparison_set.id,),
        )
        cls._insert_sessions(connection, comparison_set)

    @staticmethod
    def _insert_sessions(
        connection: Any,
        comparison_set: ComparisonSet,
    ) -> None:
        connection.executemany(
            """
            INSERT INTO comparison_set_sessions(
                comparison_set_id, session_id, role, sort_order
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (
                    comparison_set.id,
                    session_id,
                    "base"
                    if session_id == comparison_set.base_session_id
                    else "compared",
                    sort_order,
                )
                for sort_order, session_id in enumerate(comparison_set.session_ids)
            ],
        )

    @classmethod
    def _soft_delete(
        cls,
        connection: Any,
        comparison_set: ComparisonSet,
        *,
        deleted_at_utc: str | None = None,
    ) -> None:
        parameters = dict(comparison_set.parameters)
        parameters[_DELETED_AT_PARAMETER] = deleted_at_utc or _utc_now()
        connection.execute(
            """
            UPDATE comparison_sets
            SET parameters_json = ?, updated_at_utc = ?
            WHERE id = ?
            """,
            (
                _canonical_json(parameters),
                parameters[_DELETED_AT_PARAMETER],
                comparison_set.id,
            ),
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
        if cls._is_deleted_connection(connection, comparison_set_id):
            raise ValueError("deleted comparison set cannot be modified")
        run_count = cls._analysis_run_count(connection, comparison_set_id)
        if run_count:
            raise ValueError(
                "comparison set is referenced by analysis runs and cannot be modified"
            )

    @staticmethod
    def _is_deleted_connection(connection: Any, comparison_set_id: str) -> bool:
        row = connection.execute(
            "SELECT parameters_json FROM comparison_sets WHERE id = ?",
            (comparison_set_id,),
        ).fetchone()
        if row is None:
            return False
        payload = json.loads(str(row[0]))
        return isinstance(payload, dict) and bool(payload.get(_DELETED_AT_PARAMETER))

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
