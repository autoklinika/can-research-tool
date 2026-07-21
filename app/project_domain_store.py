from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .domain import (
    AnalysisInput,
    AnalysisRun,
    AnalysisStatus,
    Artifact,
    ArtifactSource,
    ClaimSource,
    ComparisonSet,
    EcuProfile,
    EcuProfileClaim,
    EvidenceReference,
    Finding,
    FindingStatus,
    VerificationStatus,
)
from .project import CrtProject
from .project_migrations import apply_project_migrations, project_schema_version


_PROFILE_FIELDS = {
    "manufacturer",
    "family",
    "model",
    "part_number",
    "serial_number",
    "vin",
    "hardware_version",
    "software_version",
    "processor",
    "state",
}

_ANALYSIS_TRANSITIONS = {
    AnalysisStatus.PENDING: {
        AnalysisStatus.RUNNING,
        AnalysisStatus.CANCELLED,
        AnalysisStatus.FAILED,
    },
    AnalysisStatus.RUNNING: {
        AnalysisStatus.COMPLETED,
        AnalysisStatus.CANCELLED,
        AnalysisStatus.FAILED,
    },
    AnalysisStatus.COMPLETED: set(),
    AnalysisStatus.CANCELLED: set(),
    AnalysisStatus.FAILED: set(),
}


class ProjectDomainStore:
    """Project-owned persistence for CRT research-domain entities.

    This repository may update only ``.crt/project.sqlite``. Session streams,
    sparse indexes and CaptureService are deliberately outside its API.
    """

    def __init__(self, project: CrtProject) -> None:
        self.project = project
        with self.project._connect() as connection:
            apply_project_migrations(connection)

    @property
    def schema_version(self) -> int:
        with self.project._connect() as connection:
            return project_schema_version(connection)

    def get_or_create_profile(self) -> EcuProfile:
        with self.project._connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, manufacturer, family, model, part_number,
                       serial_number, vin, hardware_version, software_version,
                       processor, state, created_at_utc, updated_at_utc
                FROM ecu_profiles WHERE project_id = ?
                """,
                (self.project.manifest.id,),
            ).fetchone()
            if row is not None:
                return EcuProfile(*row)

            now = _utc_now()
            profile = EcuProfile(
                id=str(uuid4()),
                project_id=self.project.manifest.id,
                created_at_utc=now,
                updated_at_utc=now,
            )
            connection.execute(
                """
                INSERT INTO ecu_profiles(
                    id, project_id, manufacturer, family, model, part_number,
                    serial_number, vin, hardware_version, software_version,
                    processor, state, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.project_id,
                    profile.manufacturer,
                    profile.family,
                    profile.model,
                    profile.part_number,
                    profile.serial_number,
                    profile.vin,
                    profile.hardware_version,
                    profile.software_version,
                    profile.processor,
                    profile.state,
                    profile.created_at_utc,
                    profile.updated_at_utc,
                ),
            )
            return profile

    def update_profile(self, **changes: str) -> EcuProfile:
        if not changes:
            return self.get_or_create_profile()
        unknown = set(changes) - _PROFILE_FIELDS
        if unknown:
            raise ValueError(f"unsupported ECU profile fields: {sorted(unknown)}")
        for field_name, value in changes.items():
            if not isinstance(value, str):
                raise TypeError(f"ECU profile field {field_name} must be text")

        profile = self.get_or_create_profile()
        assignments = ", ".join(f"{field_name} = ?" for field_name in changes)
        now = _utc_now()
        with self.project._connect() as connection:
            connection.execute(
                f"UPDATE ecu_profiles SET {assignments}, updated_at_utc = ? WHERE id = ?",
                (*changes.values(), now, profile.id),
            )
        return self.get_or_create_profile()

    def add_profile_claim(
        self,
        *,
        field_name: str,
        value: Any,
        source: ClaimSource | str,
        verification_status: VerificationStatus | str = VerificationStatus.HYPOTHESIS,
        confidence: float | None = None,
        evidence: Sequence[EvidenceReference] = (),
    ) -> EcuProfileClaim:
        if field_name not in _PROFILE_FIELDS:
            raise ValueError(f"unsupported ECU profile claim field: {field_name}")
        source_value = ClaimSource(source)
        status_value = VerificationStatus(verification_status)
        profile = self.get_or_create_profile()
        now = _utc_now()
        claim = EcuProfileClaim(
            id=str(uuid4()),
            profile_id=profile.id,
            field_name=field_name,
            value=value,
            source=source_value,
            verification_status=status_value,
            confidence=confidence,
            evidence=tuple(evidence),
            created_at_utc=now,
            updated_at_utc=now,
        )
        with self.project._connect() as connection:
            self._validate_evidence(connection, claim.evidence)
            connection.execute(
                """
                INSERT INTO ecu_profile_claims(
                    id, profile_id, field_name, value_json, source,
                    verification_status, confidence, evidence_json,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim.id,
                    claim.profile_id,
                    claim.field_name,
                    _canonical_json(claim.value),
                    claim.source.value,
                    claim.verification_status.value,
                    claim.confidence,
                    _canonical_json([item.to_dict() for item in claim.evidence]),
                    claim.created_at_utc,
                    claim.updated_at_utc,
                ),
            )
        return claim

    def create_comparison_set(
        self,
        *,
        name: str,
        session_ids: Sequence[str],
        base_session_id: str | None = None,
        synchronization_mode: str = "none",
        parameters: Mapping[str, Any] | None = None,
    ) -> ComparisonSet:
        ordered_ids = tuple(dict.fromkeys(session_ids))
        comparison = ComparisonSet(
            id=str(uuid4()),
            name=name.strip(),
            session_ids=ordered_ids,
            base_session_id=base_session_id,
            synchronization_mode=synchronization_mode.strip(),
            parameters=dict(parameters or {}),
            created_at_utc=_utc_now(),
            updated_at_utc=_utc_now(),
        )
        with self.project._connect() as connection:
            self._require_sessions(connection, comparison.session_ids)
            connection.execute(
                """
                INSERT INTO comparison_sets(
                    id, name, base_session_id, synchronization_mode,
                    parameters_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comparison.id,
                    comparison.name,
                    comparison.base_session_id,
                    comparison.synchronization_mode,
                    _canonical_json(comparison.parameters),
                    comparison.created_at_utc,
                    comparison.updated_at_utc,
                ),
            )
            connection.executemany(
                """
                INSERT INTO comparison_set_sessions(
                    comparison_set_id, session_id, role, sort_order
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        comparison.id,
                        session_id,
                        "base" if session_id == comparison.base_session_id else "compared",
                        index,
                    )
                    for index, session_id in enumerate(comparison.session_ids)
                ],
            )
        return comparison

    def create_analysis_run(
        self,
        *,
        provider_id: str,
        provider_version: str,
        algorithm_version: str,
        inputs: Sequence[AnalysisInput],
        parameters: Mapping[str, Any] | None = None,
        crt_api_version: str = "1",
    ) -> AnalysisRun:
        run = AnalysisRun(
            id=str(uuid4()),
            provider_id=provider_id.strip(),
            provider_version=provider_version.strip(),
            crt_api_version=crt_api_version.strip(),
            algorithm_version=algorithm_version.strip(),
            status=AnalysisStatus.PENDING,
            inputs=tuple(inputs),
            parameters=dict(parameters or {}),
            created_at_utc=_utc_now(),
        )
        with self.project._connect() as connection:
            for input_value in run.inputs:
                self._validate_analysis_input(connection, input_value)
            connection.execute(
                """
                INSERT INTO analysis_runs(
                    id, provider_id, provider_version, crt_api_version,
                    algorithm_version, parameters_json, status, error,
                    created_at_utc, started_at_utc, completed_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, '', '')
                """,
                (
                    run.id,
                    run.provider_id,
                    run.provider_version,
                    run.crt_api_version,
                    run.algorithm_version,
                    _canonical_json(run.parameters),
                    run.status.value,
                    run.created_at_utc,
                ),
            )
            connection.executemany(
                """
                INSERT INTO analysis_inputs(
                    analysis_run_id, sort_order, input_kind, input_id, parameters_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        run.id,
                        index,
                        item.kind,
                        item.source_id,
                        _canonical_json(item.parameters),
                    )
                    for index, item in enumerate(run.inputs)
                ],
            )
        return run

    def set_analysis_status(
        self,
        analysis_run_id: str,
        status: AnalysisStatus | str,
        *,
        error: str = "",
    ) -> None:
        target = AnalysisStatus(status)
        with self.project._connect() as connection:
            row = connection.execute(
                "SELECT status FROM analysis_runs WHERE id = ?",
                (analysis_run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown analysis run: {analysis_run_id}")
            current = AnalysisStatus(str(row[0]))
            if target == current:
                return
            if target not in _ANALYSIS_TRANSITIONS[current]:
                raise ValueError(f"invalid analysis transition: {current.value} -> {target.value}")
            now = _utc_now()
            started_at = now if target == AnalysisStatus.RUNNING else ""
            completed_at = (
                now
                if target
                in {AnalysisStatus.COMPLETED, AnalysisStatus.FAILED, AnalysisStatus.CANCELLED}
                else ""
            )
            connection.execute(
                """
                UPDATE analysis_runs
                SET status = ?, error = ?,
                    started_at_utc = CASE
                        WHEN ? != '' THEN ? ELSE started_at_utc END,
                    completed_at_utc = CASE
                        WHEN ? != '' THEN ? ELSE completed_at_utc END
                WHERE id = ?
                """,
                (
                    target.value,
                    error,
                    started_at,
                    started_at,
                    completed_at,
                    completed_at,
                    analysis_run_id,
                ),
            )

    def create_artifact(
        self,
        *,
        analysis_run_id: str,
        artifact_type: str,
        schema_version: int,
        provider_id: str,
        provider_version: str,
        algorithm_version: str,
        sources: Sequence[ArtifactSource],
        relative_path: str = "",
        sha256: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> Artifact:
        normalized_path = self._validate_relative_path(relative_path)
        artifact = Artifact(
            id=str(uuid4()),
            analysis_run_id=analysis_run_id,
            artifact_type=artifact_type.strip(),
            schema_version=schema_version,
            provider_id=provider_id.strip(),
            provider_version=provider_version.strip(),
            algorithm_version=algorithm_version.strip(),
            sources=tuple(sources),
            relative_path=normalized_path,
            sha256=sha256.strip().lower(),
            metadata=dict(metadata or {}),
            created_at_utc=_utc_now(),
        )
        with self.project._connect() as connection:
            if not self._record_exists(connection, "analysis_runs", artifact.analysis_run_id):
                raise KeyError(f"unknown analysis run: {artifact.analysis_run_id}")
            for source in artifact.sources:
                self._validate_artifact_source(connection, source)
            connection.execute(
                """
                INSERT INTO artifacts(
                    id, analysis_run_id, artifact_type, schema_version,
                    provider_id, provider_version, algorithm_version,
                    relative_path, sha256, metadata_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.id,
                    artifact.analysis_run_id,
                    artifact.artifact_type,
                    artifact.schema_version,
                    artifact.provider_id,
                    artifact.provider_version,
                    artifact.algorithm_version,
                    artifact.relative_path,
                    artifact.sha256,
                    _canonical_json(artifact.metadata),
                    artifact.created_at_utc,
                ),
            )
            connection.executemany(
                """
                INSERT INTO artifact_sources(
                    artifact_id, sort_order, session_id,
                    source_kind, source_reference_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        artifact.id,
                        index,
                        source.session_id,
                        source.source_kind,
                        _canonical_json(source.source_reference),
                    )
                    for index, source in enumerate(artifact.sources)
                ],
            )
        return artifact

    def create_finding(
        self,
        *,
        title: str,
        description: str,
        finding_type: str,
        evidence: Sequence[EvidenceReference],
        status: FindingStatus | str = FindingStatus.HYPOTHESIS,
        confidence: float | None = None,
        algorithm_id: str = "",
        algorithm_version: str = "",
        ai_provider: str = "",
        ai_model: str = "",
        operator_comment: str = "",
    ) -> Finding:
        now = _utc_now()
        finding = Finding(
            id=str(uuid4()),
            title=title.strip(),
            description=description,
            finding_type=finding_type.strip(),
            status=FindingStatus(status),
            confidence=confidence,
            evidence=tuple(evidence),
            algorithm_id=algorithm_id.strip(),
            algorithm_version=algorithm_version.strip(),
            ai_provider=ai_provider.strip(),
            ai_model=ai_model.strip(),
            operator_comment=operator_comment,
            created_at_utc=now,
            updated_at_utc=now,
        )
        with self.project._connect() as connection:
            self._validate_evidence(connection, finding.evidence)
            connection.execute(
                """
                INSERT INTO findings(
                    id, title, description, finding_type, status, confidence,
                    algorithm_id, algorithm_version, ai_provider, ai_model,
                    operator_comment, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.id,
                    finding.title,
                    finding.description,
                    finding.finding_type,
                    finding.status.value,
                    finding.confidence,
                    finding.algorithm_id,
                    finding.algorithm_version,
                    finding.ai_provider,
                    finding.ai_model,
                    finding.operator_comment,
                    finding.created_at_utc,
                    finding.updated_at_utc,
                ),
            )
            connection.executemany(
                """
                INSERT INTO finding_evidence(
                    finding_id, sort_order, evidence_kind, evidence_json
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        finding.id,
                        index,
                        item.kind,
                        _canonical_json(item.payload),
                    )
                    for index, item in enumerate(finding.evidence)
                ],
            )
            connection.execute(
                """
                INSERT INTO finding_status_history(
                    id, finding_id, old_status, new_status,
                    changed_at_utc, operator_comment
                ) VALUES (?, ?, '', ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    finding.id,
                    finding.status.value,
                    now,
                    finding.operator_comment,
                ),
            )
        return finding

    def set_finding_status(
        self,
        finding_id: str,
        status: FindingStatus | str,
        *,
        operator_comment: str = "",
    ) -> None:
        target = FindingStatus(status)
        with self.project._connect() as connection:
            row = connection.execute(
                "SELECT status FROM findings WHERE id = ?",
                (finding_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown finding: {finding_id}")
            current = FindingStatus(str(row[0]))
            if current == target and not operator_comment:
                return
            now = _utc_now()
            connection.execute(
                """
                UPDATE findings
                SET status = ?, operator_comment = ?, updated_at_utc = ?
                WHERE id = ?
                """,
                (target.value, operator_comment, now, finding_id),
            )
            connection.execute(
                """
                INSERT INTO finding_status_history(
                    id, finding_id, old_status, new_status,
                    changed_at_utc, operator_comment
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    finding_id,
                    current.value,
                    target.value,
                    now,
                    operator_comment,
                ),
            )

    def _validate_analysis_input(self, connection: Any, item: AnalysisInput) -> None:
        table_by_kind = {
            "session": "sessions",
            "comparison_set": "comparison_sets",
            "artifact": "artifacts",
        }
        table = table_by_kind.get(item.kind)
        if table is None:
            raise ValueError(f"unsupported analysis input kind: {item.kind}")
        if not self._record_exists(connection, table, item.source_id):
            raise KeyError(f"unknown {item.kind}: {item.source_id}")

    def _validate_artifact_source(self, connection: Any, source: ArtifactSource) -> None:
        frame_count = self._session_frame_count(connection, source.session_id)
        reference = dict(source.source_reference)
        if source.source_kind == "session":
            return
        if source.source_kind == "frame":
            source_row = _required_int(reference, "source_row")
            if source_row < 0 or source_row >= frame_count:
                raise ValueError("artifact frame reference is outside the session")
            return
        if source.source_kind == "frame_range":
            start = _required_int(reference, "start_source_row")
            end = _required_int(reference, "end_source_row")
            if start < 0 or end < start or end >= frame_count:
                raise ValueError("artifact frame range is outside the session")
            return
        if source.source_kind == "logical_message":
            if not reference:
                raise ValueError("logical message source reference cannot be empty")
            return
        raise ValueError(f"unsupported artifact source kind: {source.source_kind}")

    def _validate_evidence(
        self,
        connection: Any,
        evidence: Iterable[EvidenceReference],
    ) -> None:
        for item in evidence:
            payload = dict(item.payload)
            if item.kind == "frame":
                source = ArtifactSource(
                    session_id=str(payload.get("session_id", "")),
                    source_kind="frame",
                    source_reference=payload,
                )
                self._validate_artifact_source(connection, source)
            elif item.kind == "frame_range":
                source = ArtifactSource(
                    session_id=str(payload.get("session_id", "")),
                    source_kind="frame_range",
                    source_reference=payload,
                )
                self._validate_artifact_source(connection, source)
            elif item.kind == "artifact":
                artifact_id = str(payload.get("artifact_id", ""))
                if not artifact_id or not self._record_exists(connection, "artifacts", artifact_id):
                    raise KeyError(f"unknown artifact evidence: {artifact_id}")
            else:
                raise ValueError(f"unsupported evidence kind: {item.kind}")

    def _require_sessions(self, connection: Any, session_ids: Sequence[str]) -> None:
        missing = [
            session_id
            for session_id in session_ids
            if not self._record_exists(connection, "sessions", session_id)
        ]
        if missing:
            raise KeyError(f"unknown sessions: {missing}")

    def _session_frame_count(self, connection: Any, session_id: str) -> int:
        row = connection.execute(
            "SELECT frame_count FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown session: {session_id}")
        return int(row[0])

    @staticmethod
    def _record_exists(connection: Any, table: str, record_id: str) -> bool:
        allowed = {
            "sessions",
            "comparison_sets",
            "analysis_runs",
            "artifacts",
            "findings",
        }
        if table not in allowed:
            raise ValueError(f"unsupported domain table: {table}")
        return (
            connection.execute(f"SELECT 1 FROM {table} WHERE id = ?", (record_id,)).fetchone()
            is not None
        )

    def _validate_relative_path(self, relative_path: str) -> str:
        cleaned = relative_path.strip().replace("\\", "/")
        if not cleaned:
            return ""
        absolute = self.project.absolute_path(cleaned)
        if absolute == self.project.root:
            raise ValueError("artifact path must identify a file inside the project")
        return Path(cleaned).as_posix()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _required_int(payload: Mapping[str, Any], key: str) -> int:
    if key not in payload:
        raise ValueError(f"missing source reference field: {key}")
    value = payload[key]
    if isinstance(value, bool):
        raise ValueError(f"source reference field {key} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"source reference field {key} must be an integer") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
