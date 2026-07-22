from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .domain import Artifact, ArtifactSource
from .project import CrtProject


class ArtifactIntegrityError(RuntimeError):
    """Raised when persisted artifact metadata no longer matches its file."""


class ArtifactCatalog:
    """Read-only project catalog for versioned analysis artifacts."""

    def __init__(self, project: CrtProject) -> None:
        self.project = project

    def list_for_session(self, session_id: str) -> tuple[Artifact, ...]:
        cleaned = session_id.strip()
        if not cleaned:
            raise ValueError("session_id cannot be empty")
        with self.project._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT
                       a.id, a.analysis_run_id, a.artifact_type, a.schema_version,
                       a.provider_id, a.provider_version, a.algorithm_version,
                       a.relative_path, a.sha256, a.metadata_json, a.created_at_utc
                FROM artifacts AS a
                JOIN artifact_sources AS source ON source.artifact_id = a.id
                WHERE source.session_id = ?
                ORDER BY a.created_at_utc DESC, a.id DESC
                """,
                (cleaned,),
            ).fetchall()
            return tuple(self._artifact_from_row(connection, row) for row in rows)

    def get(self, artifact_id: str) -> Artifact:
        cleaned = artifact_id.strip()
        if not cleaned:
            raise ValueError("artifact_id cannot be empty")
        with self.project._connect() as connection:
            row = connection.execute(
                """
                SELECT id, analysis_run_id, artifact_type, schema_version,
                       provider_id, provider_version, algorithm_version,
                       relative_path, sha256, metadata_json, created_at_utc
                FROM artifacts WHERE id = ?
                """,
                (cleaned,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown artifact: {cleaned}")
            return self._artifact_from_row(connection, row)

    def absolute_path(self, artifact: Artifact) -> Path:
        if not artifact.relative_path:
            raise ArtifactIntegrityError(f"artifact {artifact.id} has no output file")
        path = self.project.absolute_path(artifact.relative_path)
        if not path.is_file():
            raise ArtifactIntegrityError(f"artifact file is missing: {artifact.relative_path}")
        return path

    def read_json(
        self,
        artifact: Artifact,
        *,
        maximum_bytes: int = 16 * 1024 * 1024,
    ) -> Mapping[str, Any]:
        if maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be greater than zero")
        path = self.absolute_path(artifact)
        size = path.stat().st_size
        if size > maximum_bytes:
            raise ArtifactIntegrityError(
                f"artifact is too large for direct preview: {size} bytes"
            )
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if artifact.sha256 and digest != artifact.sha256:
            raise ArtifactIntegrityError(
                f"artifact SHA-256 mismatch: expected {artifact.sha256}, got {digest}"
            )
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError(f"artifact is not valid UTF-8 JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ArtifactIntegrityError("artifact JSON root must be an object")
        return payload

    @staticmethod
    def _artifact_from_row(connection: Any, row: Any) -> Artifact:
        artifact_id = str(row[0])
        source_rows = connection.execute(
            """
            SELECT session_id, source_kind, source_reference_json
            FROM artifact_sources
            WHERE artifact_id = ?
            ORDER BY sort_order
            """,
            (artifact_id,),
        ).fetchall()
        sources = tuple(
            ArtifactSource(
                session_id=str(source_row[0]),
                source_kind=str(source_row[1]),
                source_reference=_json_mapping(source_row[2]),
            )
            for source_row in source_rows
        )
        return Artifact(
            id=artifact_id,
            analysis_run_id=str(row[1]),
            artifact_type=str(row[2]),
            schema_version=int(row[3]),
            provider_id=str(row[4]),
            provider_version=str(row[5]),
            algorithm_version=str(row[6]),
            sources=sources,
            relative_path=str(row[7] or ""),
            sha256=str(row[8] or ""),
            metadata=_json_mapping(row[9]),
            created_at_utc=str(row[10] or ""),
        )


def _json_mapping(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ArtifactIntegrityError(f"invalid artifact metadata JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArtifactIntegrityError("artifact metadata must be a JSON object")
    return payload
