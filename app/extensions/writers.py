from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.domain import (
    Artifact,
    ArtifactSource,
    EvidenceReference,
    Finding,
    FindingStatus,
)
from app.project import CrtProject
from app.project_domain_store import ProjectDomainStore

from .contracts import CancellationToken


_SAFE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ArtifactWriter:
    """Atomically writes extension output outside immutable session storage."""

    def __init__(
        self,
        *,
        project: CrtProject,
        store: ProjectDomainStore,
        analysis_run_id: str,
        provider_id: str,
        provider_version: str,
        algorithm_version: str,
        cancellation: CancellationToken,
    ) -> None:
        self._project = project
        self._store = store
        self._analysis_run_id = analysis_run_id
        self._provider_id = provider_id
        self._provider_version = provider_version
        self._algorithm_version = algorithm_version
        self._cancellation = cancellation

    def write_json(
        self,
        *,
        filename: str,
        artifact_type: str,
        schema_version: int,
        sources: Sequence[ArtifactSource],
        payload: Any,
        metadata: Mapping[str, Any] | None = None,
    ) -> Artifact:
        content = json.dumps(
            _materialize_json(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        combined_metadata = dict(metadata or {})
        combined_metadata.setdefault("encoding", "utf-8")
        combined_metadata.setdefault("media_type", "application/json")
        return self.write_bytes(
            filename=filename,
            artifact_type=artifact_type,
            schema_version=schema_version,
            sources=sources,
            content=content,
            metadata=combined_metadata,
        )

    def write_bytes(
        self,
        *,
        filename: str,
        artifact_type: str,
        schema_version: int,
        sources: Sequence[ArtifactSource],
        content: bytes,
        metadata: Mapping[str, Any] | None = None,
    ) -> Artifact:
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        safe_name = _validate_filename(filename)
        self._cancellation.raise_if_cancelled()

        output_dir = self._project.root / "artifacts" / self._analysis_run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / safe_name
        if target.exists():
            raise FileExistsError(f"artifact file already exists: {safe_name}")
        temporary = output_dir / f".{safe_name}.{uuid4().hex}.tmp"

        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            self._cancellation.raise_if_cancelled()
            temporary.replace(target)

            digest = hashlib.sha256(content).hexdigest()
            combined_metadata = dict(metadata or {})
            combined_metadata.setdefault("size_bytes", len(content))
            try:
                return self._store.create_artifact(
                    analysis_run_id=self._analysis_run_id,
                    artifact_type=artifact_type,
                    schema_version=schema_version,
                    provider_id=self._provider_id,
                    provider_version=self._provider_version,
                    algorithm_version=self._algorithm_version,
                    sources=tuple(sources),
                    relative_path=self._project.relative_path(target),
                    sha256=digest,
                    metadata=combined_metadata,
                )
            except Exception:
                target.unlink(missing_ok=True)
                raise
        finally:
            temporary.unlink(missing_ok=True)


class FindingWriter:
    """Controlled finding persistence with mandatory evidence validation."""

    def __init__(
        self,
        *,
        store: ProjectDomainStore,
        cancellation: CancellationToken,
        algorithm_id: str,
        algorithm_version: str,
    ) -> None:
        self._store = store
        self._cancellation = cancellation
        self._algorithm_id = algorithm_id
        self._algorithm_version = algorithm_version

    def create(
        self,
        *,
        title: str,
        description: str,
        finding_type: str,
        evidence: Sequence[EvidenceReference],
        status: FindingStatus | str = FindingStatus.HYPOTHESIS,
        confidence: float | None = None,
        operator_comment: str = "",
    ) -> Finding:
        self._cancellation.raise_if_cancelled()
        return self._store.create_finding(
            title=title,
            description=description,
            finding_type=finding_type,
            evidence=tuple(evidence),
            status=status,
            confidence=confidence,
            algorithm_id=self._algorithm_id,
            algorithm_version=self._algorithm_version,
            operator_comment=operator_comment,
        )


def _materialize_json(value: Any) -> Any:
    """Convert immutable Mapping/Sequence projections into JSON-native containers."""

    if isinstance(value, Mapping):
        return {str(key): _materialize_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_materialize_json(item) for item in value]
    return value


def _validate_filename(filename: str) -> str:
    cleaned = filename.strip()
    if not _SAFE_FILE_RE.fullmatch(cleaned):
        raise ValueError(
            "artifact filename must be a single safe file name without directories"
        )
    if Path(cleaned).name != cleaned:
        raise ValueError("artifact filename cannot contain a directory")
    return cleaned
