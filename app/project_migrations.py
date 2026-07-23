from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from . import sqlite_connection as sqlite3


PROJECT_DOMAIN_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ProjectMigration:
    version: int
    name: str
    statements: tuple[str, ...]


_MIGRATIONS = (
    ProjectMigration(
        version=1,
        name="project domain foundation",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS ecu_profiles(
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL UNIQUE,
                manufacturer TEXT NOT NULL DEFAULT '',
                family TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                part_number TEXT NOT NULL DEFAULT '',
                serial_number TEXT NOT NULL DEFAULT '',
                vin TEXT NOT NULL DEFAULT '',
                hardware_version TEXT NOT NULL DEFAULT '',
                software_version TEXT NOT NULL DEFAULT '',
                processor TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT '',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ecu_profile_claims(
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL REFERENCES ecu_profiles(id) ON DELETE CASCADE,
                field_name TEXT NOT NULL,
                value_json TEXT NOT NULL,
                source TEXT NOT NULL,
                verification_status TEXT NOT NULL,
                confidence REAL,
                evidence_json TEXT NOT NULL DEFAULT '[]',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                CHECK(confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS comparison_sets(
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                base_session_id TEXT REFERENCES sessions(id) ON DELETE RESTRICT,
                synchronization_mode TEXT NOT NULL DEFAULT 'none',
                parameters_json TEXT NOT NULL DEFAULT '{}',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS comparison_set_sessions(
                comparison_set_id TEXT NOT NULL
                    REFERENCES comparison_sets(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
                role TEXT NOT NULL DEFAULT 'compared',
                sort_order INTEGER NOT NULL,
                PRIMARY KEY(comparison_set_id, session_id),
                UNIQUE(comparison_set_id, sort_order)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS analysis_runs(
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                provider_version TEXT NOT NULL,
                crt_api_version TEXT NOT NULL,
                algorithm_version TEXT NOT NULL,
                parameters_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                created_at_utc TEXT NOT NULL,
                started_at_utc TEXT NOT NULL DEFAULT '',
                completed_at_utc TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS analysis_inputs(
                analysis_run_id TEXT NOT NULL
                    REFERENCES analysis_runs(id) ON DELETE CASCADE,
                sort_order INTEGER NOT NULL,
                input_kind TEXT NOT NULL,
                input_id TEXT NOT NULL,
                parameters_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(analysis_run_id, sort_order)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS artifacts(
                id TEXT PRIMARY KEY,
                analysis_run_id TEXT NOT NULL
                    REFERENCES analysis_runs(id) ON DELETE RESTRICT,
                artifact_type TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                provider_id TEXT NOT NULL,
                provider_version TEXT NOT NULL,
                algorithm_version TEXT NOT NULL,
                relative_path TEXT NOT NULL DEFAULT '',
                sha256 TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at_utc TEXT NOT NULL,
                CHECK(schema_version > 0)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS artifact_sources(
                artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
                sort_order INTEGER NOT NULL,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
                source_kind TEXT NOT NULL,
                source_reference_json TEXT NOT NULL,
                PRIMARY KEY(artifact_id, sort_order)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS findings(
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                finding_type TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence REAL,
                algorithm_id TEXT NOT NULL DEFAULT '',
                algorithm_version TEXT NOT NULL DEFAULT '',
                ai_provider TEXT NOT NULL DEFAULT '',
                ai_model TEXT NOT NULL DEFAULT '',
                operator_comment TEXT NOT NULL DEFAULT '',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                CHECK(confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS finding_evidence(
                finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
                sort_order INTEGER NOT NULL,
                evidence_kind TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                PRIMARY KEY(finding_id, sort_order)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS finding_status_history(
                id TEXT PRIMARY KEY,
                finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
                old_status TEXT NOT NULL DEFAULT '',
                new_status TEXT NOT NULL,
                changed_at_utc TEXT NOT NULL,
                operator_comment TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_profile_claims_profile_field
                ON ecu_profile_claims(profile_id, field_name)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_comparison_sessions_session
                ON comparison_set_sessions(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_provider_status
                ON analysis_runs(provider_id, status)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_inputs_source
                ON analysis_inputs(input_kind, input_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_artifacts_analysis
                ON artifacts(analysis_run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_artifact_sources_session
                ON artifact_sources(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_findings_status
                ON findings(status)
            """,
        ),
    ),
)


def apply_project_migrations(connection: sqlite3.Connection) -> int:
    """Apply additive CRT project-domain migrations to one project database.

    The immutable session files and their sidecar indexes are outside this schema
    and are never opened or modified by this function.
    """

    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations(
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at_utc TEXT NOT NULL
        )
        """
    )
    connection.commit()

    current = project_schema_version(connection)
    if current > PROJECT_DOMAIN_SCHEMA_VERSION:
        raise RuntimeError(
            "project database schema is newer than this CRT build: "
            f"{current} > {PROJECT_DOMAIN_SCHEMA_VERSION}"
        )

    for migration in _pending_migrations(current, _MIGRATIONS):
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                """
                INSERT INTO schema_migrations(version, name, applied_at_utc)
                VALUES (?, ?, ?)
                """,
                (migration.version, migration.name, _utc_now()),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return project_schema_version(connection)


def project_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    ).fetchone()
    return 0 if row is None else int(row[0])


def _pending_migrations(
    current: int,
    migrations: Iterable[ProjectMigration],
) -> tuple[ProjectMigration, ...]:
    pending = tuple(migration for migration in migrations if migration.version > current)
    expected = current + 1
    for migration in pending:
        if migration.version != expected:
            raise RuntimeError(
                f"non-contiguous project migration sequence: expected {expected}, "
                f"got {migration.version}"
            )
        expected += 1
    return pending


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
