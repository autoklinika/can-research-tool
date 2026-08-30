from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .artifact_catalog import ArtifactCatalog, ArtifactIntegrityError
from .domain import AnalysisInput, AnalysisStatus, Artifact, ArtifactSource, ComparisonSet
from .extensions import ArtifactWriter, CancellationToken, ExtensionCancelled
from .project import CrtProject, SessionRecord
from .project_domain_store import ProjectDomainStore
from .comparison_timeline import (
    ComparisonTimelineCancelled,
    ComparisonTimelineEvent,
    ComparisonTimelineLane,
    ComparisonTimelineResult,
    TimelineAnchorConfiguration,
    normalize_timeline_configuration,
)

TIMELINE_ALIGNMENT_ARTIFACT_TYPE = "comparison_timeline_alignment"
TIMELINE_ALIGNMENT_SCHEMA = "crt.comparison_timeline_alignment"
TIMELINE_ALIGNMENT_SCHEMA_VERSION = 1
TIMELINE_ALIGNMENT_PROVIDER_ID = "crt.comparison.timeline_alignment"
TIMELINE_ALIGNMENT_PROVIDER_VERSION = "1.0.0"
TIMELINE_ALIGNMENT_ALGORITHM_VERSION = "2"
_MAXIMUM_ALIGNMENT_ARTIFACT_BYTES = 128 * 1024 * 1024


class StaleComparisonTimelineArtifact(ArtifactIntegrityError):
    """Raised when a saved alignment no longer matches immutable source sessions."""


@dataclass(frozen=True, slots=True)
class StoredComparisonTimeline:
    artifact: Artifact
    result: ComparisonTimelineResult
    configuration: TimelineAnchorConfiguration


class ComparisonTimelineArtifactService:
    """Persist and reopen bounded comparison timelines as versioned artifacts."""

    def __init__(self, project: CrtProject) -> None:
        self.project = project
        self.store = ProjectDomainStore(project)
        self.catalog = ArtifactCatalog(project)

    def save(
        self,
        comparison_set: ComparisonSet,
        result: ComparisonTimelineResult,
        *,
        cancellation: CancellationToken | None = None,
    ) -> Artifact:
        token = cancellation or CancellationToken()
        token.raise_if_cancelled()
        _validate_result_matches_comparison(result, comparison_set)
        records = _records_for_comparison(self.project, comparison_set)
        configuration = result.configuration
        analysis_input = AnalysisInput(
            kind="comparison_set",
            source_id=comparison_set.id,
            parameters=configuration.to_dict(),
        )
        run = self.store.create_analysis_run(
            provider_id=TIMELINE_ALIGNMENT_PROVIDER_ID,
            provider_version=TIMELINE_ALIGNMENT_PROVIDER_VERSION,
            algorithm_version=TIMELINE_ALIGNMENT_ALGORITHM_VERSION,
            inputs=(analysis_input,),
            parameters=configuration.to_dict(),
            crt_api_version="1",
        )
        self.store.set_analysis_status(run.id, AnalysisStatus.RUNNING)
        writer = ArtifactWriter(
            project=self.project,
            store=self.store,
            analysis_run_id=run.id,
            provider_id=run.provider_id,
            provider_version=run.provider_version,
            algorithm_version=run.algorithm_version,
            cancellation=token,
        )
        try:
            payload = timeline_result_to_payload(
                comparison_set,
                result,
                records=records,
            )
            sources = tuple(
                _artifact_source(record, comparison_set, lane)
                for record, lane in zip(records, result.lanes, strict=True)
            )
            artifact = writer.write_json(
                filename="comparison-timeline-alignment.json",
                artifact_type=TIMELINE_ALIGNMENT_ARTIFACT_TYPE,
                schema_version=TIMELINE_ALIGNMENT_SCHEMA_VERSION,
                sources=sources,
                payload=payload,
                metadata={
                    "comparison_set_id": comparison_set.id,
                    "session_count": len(records),
                    "synchronization_mode": result.synchronization_mode,
                    "sampled_event_count": sum(
                        lane.sampled_frame_count for lane in result.lanes
                    ),
                    "warning_count": len(result.warnings),
                },
            )
        except (ComparisonTimelineCancelled, ExtensionCancelled):
            self.store.set_analysis_status(run.id, AnalysisStatus.CANCELLED)
            raise
        except Exception as exc:
            self.store.set_analysis_status(
                run.id,
                AnalysisStatus.FAILED,
                error=str(exc),
            )
            raise
        self.store.set_analysis_status(run.id, AnalysisStatus.COMPLETED)
        return artifact

    def load_latest_compatible(
        self,
        comparison_set: ComparisonSet,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> StoredComparisonTimeline | None:
        records = _records_for_comparison(self.project, comparison_set)
        artifacts = self.catalog.list_for_comparison_set(comparison_set.id)
        for artifact in artifacts:
            _raise_if_cancelled(should_cancel)
            if artifact.artifact_type != TIMELINE_ALIGNMENT_ARTIFACT_TYPE:
                continue
            try:
                payload = self.catalog.read_json(
                    artifact,
                    maximum_bytes=_MAXIMUM_ALIGNMENT_ARTIFACT_BYTES,
                )
                result, configuration = timeline_result_from_payload(
                    payload,
                    comparison_set=comparison_set,
                    records=records,
                )
                _raise_if_cancelled(should_cancel)
            except (ArtifactIntegrityError, KeyError, TypeError, ValueError):
                continue
            return StoredComparisonTimeline(
                artifact=artifact,
                result=result,
                configuration=configuration,
            )
        return None


def timeline_result_to_payload(
    comparison_set: ComparisonSet,
    result: ComparisonTimelineResult,
    *,
    records: tuple[SessionRecord, ...],
) -> dict[str, Any]:
    _validate_result_matches_comparison(result, comparison_set)
    if tuple(record.id for record in records) != comparison_set.session_ids:
        raise ValueError("session records do not match comparison set order")
    return {
        "schema": TIMELINE_ALIGNMENT_SCHEMA,
        "schema_version": TIMELINE_ALIGNMENT_SCHEMA_VERSION,
        "generated_by": {
            "provider_id": TIMELINE_ALIGNMENT_PROVIDER_ID,
            "provider_version": TIMELINE_ALIGNMENT_PROVIDER_VERSION,
            "algorithm_version": TIMELINE_ALIGNMENT_ALGORITHM_VERSION,
            "crt_api": "1",
        },
        "comparison_set": {
            "id": comparison_set.id,
            "name": comparison_set.name,
            "session_ids": list(comparison_set.session_ids),
            "base_session_id": comparison_set.base_session_id,
        },
        "configuration": result.configuration.to_dict(),
        "session_fingerprints": [
            {
                "session_id": record.id,
                "name": record.name,
                "frame_count": record.frame_count,
                "sha256": record.sha256,
            }
            for record in records
        ],
        "timeline": {
            "minimum_relative_time_ns": result.minimum_relative_time_ns,
            "maximum_relative_time_ns": result.maximum_relative_time_ns,
            "warnings": list(result.warnings),
            "lanes": [_lane_to_payload(lane) for lane in result.lanes],
        },
    }


def timeline_result_from_payload(
    payload: Mapping[str, Any],
    *,
    comparison_set: ComparisonSet,
    records: tuple[SessionRecord, ...],
) -> tuple[ComparisonTimelineResult, TimelineAnchorConfiguration]:
    if str(payload.get("schema") or "") != TIMELINE_ALIGNMENT_SCHEMA:
        raise ArtifactIntegrityError("unsupported comparison timeline artifact schema")
    if int(payload.get("schema_version", 0)) != TIMELINE_ALIGNMENT_SCHEMA_VERSION:
        raise ArtifactIntegrityError("unsupported comparison timeline schema version")

    comparison_payload = _mapping(payload.get("comparison_set"), "comparison_set")
    if str(comparison_payload.get("id") or "") != comparison_set.id:
        raise StaleComparisonTimelineArtifact("artifact belongs to another comparison set")
    session_ids = tuple(str(item) for item in _sequence(comparison_payload.get("session_ids")))
    if session_ids != comparison_set.session_ids:
        raise StaleComparisonTimelineArtifact("comparison set sessions changed")

    fingerprints = _sequence(payload.get("session_fingerprints"))
    if len(fingerprints) != len(records):
        raise StaleComparisonTimelineArtifact("session fingerprint count changed")
    for record, fingerprint_value in zip(records, fingerprints, strict=True):
        fingerprint = _mapping(fingerprint_value, "session fingerprint")
        if str(fingerprint.get("session_id") or "") != record.id:
            raise StaleComparisonTimelineArtifact("session order changed")
        if int(fingerprint.get("frame_count", -1)) != record.frame_count:
            raise StaleComparisonTimelineArtifact(
                f"session frame count changed: {record.name}"
            )
        saved_sha = str(fingerprint.get("sha256") or "")
        if saved_sha and record.sha256 and saved_sha != record.sha256:
            raise StaleComparisonTimelineArtifact(f"session SHA-256 changed: {record.name}")

    configuration_payload = _mapping(payload.get("configuration"), "configuration")
    configuration = normalize_timeline_configuration(
        synchronization_mode=str(
            configuration_payload.get("synchronization_mode") or ""
        ),
        anchor_message_key=str(configuration_payload.get("anchor_message_key") or ""),
        anchor_marker_name=str(configuration_payload.get("anchor_marker_name") or ""),
        anchor_occurrence=int(configuration_payload.get("anchor_occurrence", 1)),
        explicit_anchor_rows={
            str(session_id): int(source_row)
            for session_id, source_row in _mapping(
                configuration_payload.get("explicit_anchor_rows", {}),
                "explicit_anchor_rows",
            ).items()
        },
    )

    timeline = _mapping(payload.get("timeline"), "timeline")
    lanes = tuple(_lane_from_payload(value) for value in _sequence(timeline.get("lanes")))
    if tuple(lane.session_id for lane in lanes) != comparison_set.session_ids:
        raise StaleComparisonTimelineArtifact("artifact lane order changed")
    result = ComparisonTimelineResult(
        synchronization_mode=configuration.synchronization_mode,
        anchor_message_key=configuration.anchor_message_key,
        anchor_marker_name=configuration.anchor_marker_name,
        anchor_occurrence=configuration.anchor_occurrence,
        explicit_anchor_rows=configuration.explicit_anchor_rows,
        lanes=lanes,
        warnings=tuple(str(item) for item in _sequence(timeline.get("warnings", []))),
        minimum_relative_time_ns=int(timeline.get("minimum_relative_time_ns", 0)),
        maximum_relative_time_ns=int(timeline.get("maximum_relative_time_ns", 1)),
    )
    _validate_result_matches_comparison(result, comparison_set)
    return result, configuration


def _lane_to_payload(lane: ComparisonTimelineLane) -> dict[str, Any]:
    return {
        "session_id": lane.session_id,
        "session_name": lane.session_name,
        "total_frame_count": lane.total_frame_count,
        "sampled_frame_count": lane.sampled_frame_count,
        "sample_stride": lane.sample_stride,
        "anchor_source_row": lane.anchor_source_row,
        "anchor_timestamp_ns": lane.anchor_timestamp_ns,
        "first_timestamp_ns": lane.first_timestamp_ns,
        "last_timestamp_ns": lane.last_timestamp_ns,
        "synchronized": lane.synchronized,
        "warning": lane.warning,
        "anchor_kind": lane.anchor_kind,
        "anchor_label": lane.anchor_label,
        "anchor_reference": dict(lane.anchor_reference),
        "events": [
            {
                "session_id": event.session_id,
                "session_name": event.session_name,
                "source_row": event.source_row,
                "sequence": event.sequence,
                "timestamp_ns": event.timestamp_ns,
                "relative_time_ns": event.relative_time_ns,
                "message_key": event.message_key,
                "data_hex": event.data_hex,
                "dlc": event.dlc,
            }
            for event in lane.events
        ],
    }


def _lane_from_payload(value: Any) -> ComparisonTimelineLane:
    payload = _mapping(value, "timeline lane")
    session_id = str(payload.get("session_id") or "")
    events = tuple(
        _event_from_payload(item, expected_session_id=session_id)
        for item in _sequence(payload.get("events", []))
    )
    sampled_count = int(payload.get("sampled_frame_count", len(events)))
    if sampled_count != len(events):
        raise ArtifactIntegrityError("timeline sampled_frame_count mismatch")
    return ComparisonTimelineLane(
        session_id=session_id,
        session_name=str(payload.get("session_name") or session_id),
        total_frame_count=int(payload.get("total_frame_count", 0)),
        sampled_frame_count=sampled_count,
        sample_stride=int(payload.get("sample_stride", 1)),
        anchor_source_row=_optional_int(payload.get("anchor_source_row")),
        anchor_timestamp_ns=_optional_int(payload.get("anchor_timestamp_ns")),
        first_timestamp_ns=_optional_int(payload.get("first_timestamp_ns")),
        last_timestamp_ns=_optional_int(payload.get("last_timestamp_ns")),
        synchronized=bool(payload.get("synchronized", False)),
        warning=str(payload.get("warning") or ""),
        events=events,
        anchor_kind=str(payload.get("anchor_kind") or ""),
        anchor_label=str(payload.get("anchor_label") or ""),
        anchor_reference=_mapping(
            payload.get("anchor_reference", {}),
            "anchor_reference",
        ),
    )


def _event_from_payload(value: Any, *, expected_session_id: str) -> ComparisonTimelineEvent:
    payload = _mapping(value, "timeline event")
    session_id = str(payload.get("session_id") or "")
    if session_id != expected_session_id:
        raise ArtifactIntegrityError("timeline event belongs to another lane")
    source_row = int(payload.get("source_row", -1))
    if source_row < 0:
        raise ArtifactIntegrityError("timeline event source_row cannot be negative")
    return ComparisonTimelineEvent(
        session_id=session_id,
        session_name=str(payload.get("session_name") or session_id),
        source_row=source_row,
        sequence=int(payload.get("sequence", 0)),
        timestamp_ns=int(payload.get("timestamp_ns", 0)),
        relative_time_ns=_optional_int(payload.get("relative_time_ns")),
        message_key=str(payload.get("message_key") or ""),
        data_hex=str(payload.get("data_hex") or ""),
        dlc=int(payload.get("dlc", 0)),
    )


def _artifact_source(
    record: SessionRecord,
    comparison_set: ComparisonSet,
    lane: ComparisonTimelineLane,
) -> ArtifactSource:
    return ArtifactSource(
        session_id=record.id,
        source_kind="session",
        source_reference={
            "comparison_set_id": comparison_set.id,
            "role": (
                "base" if record.id == comparison_set.base_session_id else "compared"
            ),
            "frame_count": record.frame_count,
            "sha256": record.sha256,
            "synchronization_mode": lane.anchor_kind,
            "anchor_source_row": lane.anchor_source_row,
            "anchor_timestamp_ns": lane.anchor_timestamp_ns,
            "anchor_reference": dict(lane.anchor_reference),
        },
    )


def _records_for_comparison(
    project: CrtProject,
    comparison_set: ComparisonSet,
) -> tuple[SessionRecord, ...]:
    records = {record.id: record for record in project.list_sessions()}
    missing = [session_id for session_id in comparison_set.session_ids if session_id not in records]
    if missing:
        raise KeyError(f"comparison sessions are missing: {missing}")
    return tuple(records[session_id] for session_id in comparison_set.session_ids)


def _validate_result_matches_comparison(
    result: ComparisonTimelineResult,
    comparison_set: ComparisonSet,
) -> None:
    if tuple(lane.session_id for lane in result.lanes) != comparison_set.session_ids:
        raise ValueError("timeline lanes do not match comparison set session order")
    if result.minimum_relative_time_ns > result.maximum_relative_time_ns:
        raise ValueError("timeline relative time range is inverted")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ArtifactIntegrityError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _sequence(value: Any) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise ArtifactIntegrityError("artifact value must be an array")
    return list(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _raise_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise ComparisonTimelineCancelled


__all__ = [
    "ComparisonTimelineArtifactService",
    "StaleComparisonTimelineArtifact",
    "StoredComparisonTimeline",
    "TIMELINE_ALIGNMENT_ALGORITHM_VERSION",
    "TIMELINE_ALIGNMENT_ARTIFACT_TYPE",
    "TIMELINE_ALIGNMENT_PROVIDER_ID",
    "TIMELINE_ALIGNMENT_PROVIDER_VERSION",
    "TIMELINE_ALIGNMENT_SCHEMA",
    "TIMELINE_ALIGNMENT_SCHEMA_VERSION",
    "timeline_result_from_payload",
    "timeline_result_to_payload",
]
