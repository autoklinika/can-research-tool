from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .artifact_catalog import ArtifactIntegrityError
from .comparison_uds_latency import (
    UDS_LATENCY_ARTIFACT_TYPE,
    ComparisonUdsLatencyService,
    StoredUdsLatency,
    UdsLatencyCancelled,
    _records_for_comparison,
    uds_latency_result_from_payload,
)
from .domain import ComparisonSet

_MAXIMUM_ARTIFACT_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PreferredUdsLatencySource:
    stored: StoredUdsLatency | None
    evidence_count: int
    skipped_newer_empty_artifacts: int


def load_preferred_uds_latency_source(
    service: ComparisonUdsLatencyService,
    comparison_set: ComparisonSet,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> PreferredUdsLatencySource:
    """Load the newest compatible UDS artifact that contains transaction evidence.

    Stage 2C2 may create several valid artifacts for the same comparison set and
    different request/response key pairs. A later run with keys that are absent
    from the sessions is still a valid, but empty, artifact. The explorer should
    not let such an artifact hide an older result that contains evidence.

    If no compatible artifact contains evidence, the newest valid empty artifact
    is returned as an explicit fallback so the GUI can explain why it is empty.
    """

    records = _records_for_comparison(service.project, comparison_set)
    newest_valid_empty: StoredUdsLatency | None = None
    newer_empty_count = 0

    for artifact in service.catalog.list_for_comparison_set(comparison_set.id):
        _raise_if_cancelled(should_cancel)
        if artifact.artifact_type != UDS_LATENCY_ARTIFACT_TYPE:
            continue
        try:
            payload = service.catalog.read_json(
                artifact,
                maximum_bytes=_MAXIMUM_ARTIFACT_BYTES,
            )
            result = uds_latency_result_from_payload(
                payload,
                comparison_set=comparison_set,
                records=records,
            )
            _raise_if_cancelled(should_cancel)
        except (ArtifactIntegrityError, KeyError, TypeError, ValueError):
            continue

        stored = StoredUdsLatency(artifact=artifact, result=result)
        evidence_count = sum(
            len(session.transaction_evidence) for session in result.sessions
        )
        if evidence_count > 0:
            return PreferredUdsLatencySource(
                stored=stored,
                evidence_count=evidence_count,
                skipped_newer_empty_artifacts=newer_empty_count,
            )

        if newest_valid_empty is None:
            newest_valid_empty = stored
        newer_empty_count += 1

    return PreferredUdsLatencySource(
        stored=newest_valid_empty,
        evidence_count=0,
        skipped_newer_empty_artifacts=0,
    )


def _raise_if_cancelled(
    should_cancel: Callable[[], bool] | None,
) -> None:
    if should_cancel is not None and should_cancel():
        raise UdsLatencyCancelled("UDS explorer source loading cancelled")


__all__ = [
    "PreferredUdsLatencySource",
    "load_preferred_uds_latency_source",
]
