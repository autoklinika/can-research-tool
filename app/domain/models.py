from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


JsonMapping = Mapping[str, Any]


class ClaimSource(StrEnum):
    USER = "user"
    DIAGNOSTIC = "diagnostic"
    DETERMINISTIC_ANALYSIS = "deterministic_analysis"
    AI = "ai"


class VerificationStatus(StrEnum):
    HYPOTHESIS = "hypothesis"
    TO_VERIFY = "to_verify"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FindingStatus(StrEnum):
    HYPOTHESIS = "hypothesis"
    TO_VERIFY = "to_verify"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class FrameReference:
    session_id: str
    source_row: int
    sequence: int | None = None
    timestamp_ns: int | None = None

    def __post_init__(self) -> None:
        _require_text(self.session_id, "session_id")
        if self.source_row < 0:
            raise ValueError("source_row cannot be negative")
        if self.sequence is not None and self.sequence < 0:
            raise ValueError("sequence cannot be negative")
        if self.timestamp_ns is not None and self.timestamp_ns < 0:
            raise ValueError("timestamp_ns cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "source_row": self.source_row,
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass(frozen=True, slots=True)
class FrameRangeReference:
    session_id: str
    start_source_row: int
    end_source_row: int

    def __post_init__(self) -> None:
        _require_text(self.session_id, "session_id")
        if self.start_source_row < 0:
            raise ValueError("start_source_row cannot be negative")
        if self.end_source_row < self.start_source_row:
            raise ValueError("end_source_row cannot precede start_source_row")

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "start_source_row": self.start_source_row,
            "end_source_row": self.end_source_row,
        }


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    kind: str
    payload: JsonMapping

    def __post_init__(self) -> None:
        _require_text(self.kind, "kind")

    @classmethod
    def frame(cls, reference: FrameReference) -> "EvidenceReference":
        return cls(kind="frame", payload=reference.to_dict())

    @classmethod
    def frame_range(cls, reference: FrameRangeReference) -> "EvidenceReference":
        return cls(kind="frame_range", payload=reference.to_dict())

    @classmethod
    def artifact(cls, artifact_id: str) -> "EvidenceReference":
        _require_text(artifact_id, "artifact_id")
        return cls(kind="artifact", payload={"artifact_id": artifact_id})

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "payload": dict(self.payload)}


@dataclass(frozen=True, slots=True)
class EcuProfile:
    id: str
    project_id: str
    manufacturer: str = ""
    family: str = ""
    model: str = ""
    part_number: str = ""
    serial_number: str = ""
    vin: str = ""
    hardware_version: str = ""
    software_version: str = ""
    processor: str = ""
    state: str = ""
    created_at_utc: str = ""
    updated_at_utc: str = ""

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.project_id, "project_id")


@dataclass(frozen=True, slots=True)
class EcuProfileClaim:
    id: str
    profile_id: str
    field_name: str
    value: Any
    source: ClaimSource
    verification_status: VerificationStatus
    confidence: float | None = None
    evidence: tuple[EvidenceReference, ...] = ()
    created_at_utc: str = ""
    updated_at_utc: str = ""

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.profile_id, "profile_id")
        _require_text(self.field_name, "field_name")
        _validate_confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class ComparisonSet:
    id: str
    name: str
    session_ids: tuple[str, ...]
    base_session_id: str | None = None
    synchronization_mode: str = "none"
    parameters: JsonMapping = field(default_factory=dict)
    created_at_utc: str = ""
    updated_at_utc: str = ""

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.name, "name")
        if len(self.session_ids) < 2:
            raise ValueError("comparison set requires at least two sessions")
        if len(set(self.session_ids)) != len(self.session_ids):
            raise ValueError("comparison set session_ids must be unique")
        for session_id in self.session_ids:
            _require_text(session_id, "session_id")
        if self.base_session_id is not None and self.base_session_id not in self.session_ids:
            raise ValueError("base_session_id must belong to session_ids")
        _require_text(self.synchronization_mode, "synchronization_mode")


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    kind: str
    source_id: str
    parameters: JsonMapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.kind, "kind")
        _require_text(self.source_id, "source_id")


@dataclass(frozen=True, slots=True)
class AnalysisRun:
    id: str
    provider_id: str
    provider_version: str
    crt_api_version: str
    algorithm_version: str
    status: AnalysisStatus
    inputs: tuple[AnalysisInput, ...]
    parameters: JsonMapping = field(default_factory=dict)
    error: str = ""
    created_at_utc: str = ""
    started_at_utc: str = ""
    completed_at_utc: str = ""

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.provider_id, "provider_id")
        _require_text(self.provider_version, "provider_version")
        _require_text(self.crt_api_version, "crt_api_version")
        _require_text(self.algorithm_version, "algorithm_version")
        if not self.inputs:
            raise ValueError("analysis run requires at least one input")


@dataclass(frozen=True, slots=True)
class ArtifactSource:
    session_id: str
    source_kind: str
    source_reference: JsonMapping

    def __post_init__(self) -> None:
        _require_text(self.session_id, "session_id")
        _require_text(self.source_kind, "source_kind")


@dataclass(frozen=True, slots=True)
class Artifact:
    id: str
    analysis_run_id: str
    artifact_type: str
    schema_version: int
    provider_id: str
    provider_version: str
    algorithm_version: str
    sources: tuple[ArtifactSource, ...]
    relative_path: str = ""
    sha256: str = ""
    metadata: JsonMapping = field(default_factory=dict)
    created_at_utc: str = ""

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.analysis_run_id, "analysis_run_id")
        _require_text(self.artifact_type, "artifact_type")
        _require_text(self.provider_id, "provider_id")
        _require_text(self.provider_version, "provider_version")
        _require_text(self.algorithm_version, "algorithm_version")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be greater than zero")
        if not self.sources:
            raise ValueError("artifact requires at least one source")


@dataclass(frozen=True, slots=True)
class Finding:
    id: str
    title: str
    description: str
    finding_type: str
    status: FindingStatus
    confidence: float | None
    evidence: tuple[EvidenceReference, ...]
    algorithm_id: str = ""
    algorithm_version: str = ""
    ai_provider: str = ""
    ai_model: str = ""
    operator_comment: str = ""
    created_at_utc: str = ""
    updated_at_utc: str = ""

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.title, "title")
        _require_text(self.finding_type, "finding_type")
        _validate_confidence(self.confidence)
        if not self.evidence:
            raise ValueError("finding requires at least one evidence reference")


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _validate_confidence(value: float | None) -> None:
    if value is not None and not 0.0 <= float(value) <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")
