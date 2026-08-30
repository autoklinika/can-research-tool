from __future__ import annotations

import hashlib
import heapq
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .artifact_catalog import ArtifactCatalog, ArtifactIntegrityError
from .comparison_timeline import format_timeline_message_key, parse_timeline_message_key
from .domain import AnalysisInput, AnalysisStatus, Artifact, ArtifactSource, ComparisonSet
from .extensions import ArtifactWriter, CancellationToken, ExtensionCancelled
from .project import CrtProject, SessionRecord
from .project_domain_store import ProjectDomainStore
from .session_stream import SessionPagedReader

INTERFRAME_TIMING_ARTIFACT_TYPE = "comparison_interframe_timing"
INTERFRAME_TIMING_SCHEMA = "crt.comparison_interframe_timing"
INTERFRAME_TIMING_SCHEMA_VERSION = 1
INTERFRAME_TIMING_PROVIDER_ID = "crt.comparison.interframe_timing"
INTERFRAME_TIMING_PROVIDER_VERSION = "1.0.0"
INTERFRAME_TIMING_ALGORITHM_VERSION = "1"
DEFAULT_PERCENTILE_SAMPLE_LIMIT = 100_000
DEFAULT_MAXIMUM_GAP_EVIDENCE = 100
DEFAULT_GAP_FACTOR = 3.0
_MAXIMUM_ARTIFACT_BYTES = 128 * 1024 * 1024
_CANCEL_STRIDE = 1_024


class InterFrameTimingCancelled(RuntimeError):
    """Raised when passive timing analysis is cancelled."""


class StaleInterFrameTimingArtifact(ArtifactIntegrityError):
    """Raised when a saved timing artifact no longer matches source sessions."""


@dataclass(frozen=True, slots=True)
class InterFrameGapEvidence:
    session_id: str
    session_name: str
    message_key: str
    previous_source_row: int
    current_source_row: int
    previous_timestamp_ns: int
    current_timestamp_ns: int
    interval_ns: int
    threshold_ns: float
    ratio_to_nominal: float


@dataclass(frozen=True, slots=True)
class InterFrameSessionStatistics:
    session_id: str
    session_name: str
    message_key: str
    occurrence_count: int
    positive_interval_count: int
    non_positive_interval_count: int
    first_source_row: int | None
    last_source_row: int | None
    minimum_interval_ns: int | None
    maximum_interval_ns: int | None
    mean_interval_ns: float | None
    standard_deviation_ns: float | None
    p05_interval_ns: float | None
    p25_interval_ns: float | None
    median_interval_ns: float | None
    p75_interval_ns: float | None
    p95_interval_ns: float | None
    p99_interval_ns: float | None
    jitter_p95_p05_ns: float | None
    jitter_rms_from_median_ns: float | None
    coefficient_of_variation_percent: float | None
    nominal_frequency_hz: float | None
    gap_threshold_ns: float | None
    gap_count: int
    percentile_sample_count: int
    gap_evidence: tuple[InterFrameGapEvidence, ...]
    warning: str = ""


@dataclass(frozen=True, slots=True)
class InterFrameSessionComparison:
    session_id: str
    session_name: str
    baseline_session_id: str
    mean_interval_delta_percent: float | None
    median_interval_delta_percent: float | None
    jitter_delta_percent: float | None
    frequency_delta_percent: float | None
    coefficient_of_variation_delta_percentage_points: float | None
    gap_count_delta: int


@dataclass(frozen=True, slots=True)
class InterFrameTimingResult:
    message_key: str
    gap_factor: float
    percentile_sample_limit: int
    maximum_gap_evidence_per_session: int
    baseline_session_id: str
    sessions: tuple[InterFrameSessionStatistics, ...]
    comparisons: tuple[InterFrameSessionComparison, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InterFrameTimingExecutionResult:
    result: InterFrameTimingResult
    artifact: Artifact


@dataclass(frozen=True, slots=True)
class StoredInterFrameTiming:
    artifact: Artifact
    result: InterFrameTimingResult


@dataclass(slots=True)
class _FirstPass:
    occurrence_count: int = 0
    positive_interval_count: int = 0
    non_positive_interval_count: int = 0
    first_source_row: int | None = None
    last_source_row: int | None = None
    minimum_interval_ns: int | None = None
    maximum_interval_ns: int | None = None
    mean_interval_ns: float = 0.0
    m2_interval_ns: float = 0.0
    sample: list[int] | None = None


class ComparisonInterFrameTimingService:
    """Passive, bounded inter-frame timing analysis for one exact CAN key."""

    def __init__(self, project: CrtProject) -> None:
        self.project = project
        self.store = ProjectDomainStore(project)
        self.catalog = ArtifactCatalog(project)

    def run_and_save(
        self,
        comparison_set: ComparisonSet,
        message_key: str,
        *,
        gap_factor: float = DEFAULT_GAP_FACTOR,
        percentile_sample_limit: int = DEFAULT_PERCENTILE_SAMPLE_LIMIT,
        maximum_gap_evidence_per_session: int = DEFAULT_MAXIMUM_GAP_EVIDENCE,
        cancellation: CancellationToken | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> InterFrameTimingExecutionResult:
        token = cancellation or CancellationToken()
        normalized_key = format_timeline_message_key(parse_timeline_message_key(message_key))
        parameters = {
            "message_key": normalized_key,
            "gap_factor": float(gap_factor),
            "percentile_sample_limit": int(percentile_sample_limit),
            "maximum_gap_evidence_per_session": int(maximum_gap_evidence_per_session),
        }
        analysis_input = AnalysisInput(
            kind="comparison_set",
            source_id=comparison_set.id,
            parameters=parameters,
        )
        run = self.store.create_analysis_run(
            provider_id=INTERFRAME_TIMING_PROVIDER_ID,
            provider_version=INTERFRAME_TIMING_PROVIDER_VERSION,
            algorithm_version=INTERFRAME_TIMING_ALGORITHM_VERSION,
            inputs=(analysis_input,),
            parameters=parameters,
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
            result = analyze_comparison_interframe_timing(
                self.project,
                comparison_set,
                normalized_key,
                gap_factor=gap_factor,
                percentile_sample_limit=percentile_sample_limit,
                maximum_gap_evidence_per_session=maximum_gap_evidence_per_session,
                should_cancel=lambda: token.is_cancelled,
                progress_callback=progress_callback,
            )
            records = _records_for_comparison(self.project, comparison_set)
            artifact = writer.write_json(
                filename="comparison-interframe-timing.json",
                artifact_type=INTERFRAME_TIMING_ARTIFACT_TYPE,
                schema_version=INTERFRAME_TIMING_SCHEMA_VERSION,
                sources=tuple(
                    ArtifactSource(
                        session_id=record.id,
                        source_kind="session",
                        source_reference={
                            "comparison_set_id": comparison_set.id,
                            "role": "base" if record.id == result.baseline_session_id else "compared",
                            "frame_count": record.frame_count,
                            "sha256": record.sha256,
                            "message_key": result.message_key,
                        },
                    )
                    for record in records
                ),
                payload=interframe_timing_result_to_payload(
                    comparison_set,
                    result,
                    records=records,
                ),
                metadata={
                    "comparison_set_id": comparison_set.id,
                    "message_key": result.message_key,
                    "session_count": len(result.sessions),
                    "gap_count": sum(item.gap_count for item in result.sessions),
                    "warning_count": len(result.warnings),
                },
            )
        except (InterFrameTimingCancelled, ExtensionCancelled):
            self.store.set_analysis_status(run.id, AnalysisStatus.CANCELLED)
            raise
        except Exception as exc:
            self.store.set_analysis_status(run.id, AnalysisStatus.FAILED, error=str(exc))
            raise
        self.store.set_analysis_status(run.id, AnalysisStatus.COMPLETED)
        return InterFrameTimingExecutionResult(result=result, artifact=artifact)

    def load_latest_compatible(
        self,
        comparison_set: ComparisonSet,
        *,
        message_key: str = "",
        should_cancel: Callable[[], bool] | None = None,
    ) -> StoredInterFrameTiming | None:
        normalized_key = (
            format_timeline_message_key(parse_timeline_message_key(message_key))
            if str(message_key).strip()
            else ""
        )
        records = _records_for_comparison(self.project, comparison_set)
        for artifact in self.catalog.list_for_comparison_set(comparison_set.id):
            _raise_if_cancelled(should_cancel)
            if artifact.artifact_type != INTERFRAME_TIMING_ARTIFACT_TYPE:
                continue
            if normalized_key and str(artifact.metadata.get("message_key") or "") != normalized_key:
                continue
            try:
                payload = self.catalog.read_json(
                    artifact,
                    maximum_bytes=_MAXIMUM_ARTIFACT_BYTES,
                )
                result = interframe_timing_result_from_payload(
                    payload,
                    comparison_set=comparison_set,
                    records=records,
                )
                _raise_if_cancelled(should_cancel)
            except (ArtifactIntegrityError, KeyError, TypeError, ValueError):
                continue
            return StoredInterFrameTiming(artifact=artifact, result=result)
        return None


def analyze_comparison_interframe_timing(
    project: CrtProject,
    comparison_set: ComparisonSet,
    message_key: str,
    *,
    gap_factor: float = DEFAULT_GAP_FACTOR,
    percentile_sample_limit: int = DEFAULT_PERCENTILE_SAMPLE_LIMIT,
    maximum_gap_evidence_per_session: int = DEFAULT_MAXIMUM_GAP_EVIDENCE,
    should_cancel: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> InterFrameTimingResult:
    parsed_key = parse_timeline_message_key(message_key)
    normalized_key = format_timeline_message_key(parsed_key)
    gap_factor = float(gap_factor)
    percentile_sample_limit = int(percentile_sample_limit)
    maximum_gap_evidence_per_session = int(maximum_gap_evidence_per_session)
    if gap_factor <= 1.0:
        raise ValueError("gap_factor must be greater than 1.0")
    if percentile_sample_limit < 128:
        raise ValueError("percentile_sample_limit must be at least 128")
    if maximum_gap_evidence_per_session <= 0:
        raise ValueError("maximum_gap_evidence_per_session must be greater than zero")

    records = _records_for_comparison(project, comparison_set)
    total_work = max(1, sum(max(0, record.frame_count) for record in records) * 2)
    progress = 0
    sessions: list[InterFrameSessionStatistics] = []
    warnings: list[str] = []

    for record in records:
        _raise_if_cancelled(should_cancel)
        first, consumed = _first_pass(
            project,
            record,
            parsed_key,
            normalized_key,
            percentile_sample_limit,
            should_cancel,
            progress_callback,
            progress,
            total_work,
        )
        progress += consumed
        stats, consumed = _second_pass(
            project,
            record,
            parsed_key,
            normalized_key,
            first,
            gap_factor,
            maximum_gap_evidence_per_session,
            should_cancel,
            progress_callback,
            progress,
            total_work,
        )
        progress += consumed
        sessions.append(stats)
        if stats.warning:
            warnings.append(stats.warning)

    baseline_id = comparison_set.base_session_id or comparison_set.session_ids[0]
    baseline = next(item for item in sessions if item.session_id == baseline_id)
    comparisons = tuple(
        _compare_session(baseline, item)
        for item in sessions
        if item.session_id != baseline_id
    )
    if progress_callback is not None:
        progress_callback(total_work, total_work, "Zapisuję wynik timingów i jitteru")
    return InterFrameTimingResult(
        message_key=normalized_key,
        gap_factor=gap_factor,
        percentile_sample_limit=percentile_sample_limit,
        maximum_gap_evidence_per_session=maximum_gap_evidence_per_session,
        baseline_session_id=baseline_id,
        sessions=tuple(sessions),
        comparisons=comparisons,
        warnings=tuple(warnings),
    )


def _first_pass(
    project: CrtProject,
    record: SessionRecord,
    parsed_key,
    message_key: str,
    sample_limit: int,
    should_cancel: Callable[[], bool] | None,
    progress_callback: Callable[[int, int, str], None] | None,
    progress_offset: int,
    total_work: int,
) -> tuple[_FirstPass, int]:
    reader = SessionPagedReader(project.absolute_path(record.relative_path))
    state = _FirstPass(sample=[])
    previous_timestamp: int | None = None
    seed = int.from_bytes(
        hashlib.blake2b(
            f"{record.id}|{message_key}".encode("utf-8"),
            digest_size=8,
        ).digest(),
        "big",
    )
    consumed = 0
    for source_row, frame in enumerate(reader.iter_frames()):
        consumed += 1
        if source_row % _CANCEL_STRIDE == 0:
            _raise_if_cancelled(should_cancel)
            if progress_callback is not None:
                progress_callback(
                    min(total_work, progress_offset + consumed),
                    total_work,
                    f"Pierwszy przebieg: {record.name}",
                )
        if not _frame_matches(frame, parsed_key):
            continue
        timestamp = int(frame.timestamp_ns)
        if state.first_source_row is None:
            state.first_source_row = source_row
        state.last_source_row = source_row
        state.occurrence_count += 1
        if previous_timestamp is not None:
            interval = timestamp - previous_timestamp
            if interval <= 0:
                state.non_positive_interval_count += 1
            else:
                state.positive_interval_count += 1
                state.minimum_interval_ns = (
                    interval
                    if state.minimum_interval_ns is None
                    else min(state.minimum_interval_ns, interval)
                )
                state.maximum_interval_ns = (
                    interval
                    if state.maximum_interval_ns is None
                    else max(state.maximum_interval_ns, interval)
                )
                delta = interval - state.mean_interval_ns
                state.mean_interval_ns += delta / state.positive_interval_count
                state.m2_interval_ns += delta * (interval - state.mean_interval_ns)
                _reservoir_add(
                    state.sample,
                    interval,
                    state.positive_interval_count,
                    sample_limit,
                    seed,
                )
        previous_timestamp = timestamp
    _raise_if_cancelled(should_cancel)
    return state, consumed


def _second_pass(
    project: CrtProject,
    record: SessionRecord,
    parsed_key,
    message_key: str,
    first: _FirstPass,
    gap_factor: float,
    maximum_evidence: int,
    should_cancel: Callable[[], bool] | None,
    progress_callback: Callable[[int, int, str], None] | None,
    progress_offset: int,
    total_work: int,
) -> tuple[InterFrameSessionStatistics, int]:
    sample = sorted(first.sample or [])
    p05 = _percentile(sample, 5)
    p25 = _percentile(sample, 25)
    median = _percentile(sample, 50)
    p75 = _percentile(sample, 75)
    p95 = _percentile(sample, 95)
    p99 = _percentile(sample, 99)
    gap_threshold = None if median is None else median * gap_factor
    standard_deviation = (
        math.sqrt(first.m2_interval_ns / first.positive_interval_count)
        if first.positive_interval_count > 0
        else None
    )
    coefficient = (
        standard_deviation / first.mean_interval_ns * 100.0
        if standard_deviation is not None and first.mean_interval_ns > 0
        else None
    )
    nominal_frequency = (
        1_000_000_000.0 / median
        if median is not None and median > 0
        else None
    )

    reader = SessionPagedReader(project.absolute_path(record.relative_path))
    previous_timestamp: int | None = None
    previous_source_row: int | None = None
    gap_count = 0
    median_square_sum = 0.0
    heap: list[tuple[int, int, int, int, int]] = []
    consumed = 0
    for source_row, frame in enumerate(reader.iter_frames()):
        consumed += 1
        if source_row % _CANCEL_STRIDE == 0:
            _raise_if_cancelled(should_cancel)
            if progress_callback is not None:
                progress_callback(
                    min(total_work, progress_offset + consumed),
                    total_work,
                    f"Drugi przebieg: {record.name}",
                )
        if not _frame_matches(frame, parsed_key):
            continue
        timestamp = int(frame.timestamp_ns)
        if previous_timestamp is not None and previous_source_row is not None:
            interval = timestamp - previous_timestamp
            if interval > 0 and median is not None:
                median_square_sum += (interval - median) ** 2
                if gap_threshold is not None and interval >= gap_threshold:
                    gap_count += 1
                    evidence_value = (
                        interval,
                        source_row,
                        previous_source_row,
                        previous_timestamp,
                        timestamp,
                    )
                    if len(heap) < maximum_evidence:
                        heapq.heappush(heap, evidence_value)
                    elif evidence_value > heap[0]:
                        heapq.heapreplace(heap, evidence_value)
        previous_timestamp = timestamp
        previous_source_row = source_row
    _raise_if_cancelled(should_cancel)

    gap_evidence = tuple(
        InterFrameGapEvidence(
            session_id=record.id,
            session_name=record.name,
            message_key=message_key,
            previous_source_row=previous_row,
            current_source_row=current_row,
            previous_timestamp_ns=previous_timestamp_ns,
            current_timestamp_ns=current_timestamp_ns,
            interval_ns=interval,
            threshold_ns=float(gap_threshold or 0.0),
            ratio_to_nominal=(interval / median if median and median > 0 else 0.0),
        )
        for interval, current_row, previous_row, previous_timestamp_ns, current_timestamp_ns in sorted(
            heap,
            reverse=True,
        )
    )
    warning = ""
    if first.occurrence_count == 0:
        warning = f"Sesja {record.name!r} nie zawiera klucza {message_key}."
    elif first.positive_interval_count == 0:
        warning = (
            f"Sesja {record.name!r} nie zawiera co najmniej dwóch rosnących "
            f"timestampów dla {message_key}."
        )
    elif first.non_positive_interval_count:
        warning = (
            f"Sesja {record.name!r}: pominięto {first.non_positive_interval_count} "
            "niemonotonicznych odstępów."
        )

    return (
        InterFrameSessionStatistics(
            session_id=record.id,
            session_name=record.name,
            message_key=message_key,
            occurrence_count=first.occurrence_count,
            positive_interval_count=first.positive_interval_count,
            non_positive_interval_count=first.non_positive_interval_count,
            first_source_row=first.first_source_row,
            last_source_row=first.last_source_row,
            minimum_interval_ns=first.minimum_interval_ns,
            maximum_interval_ns=first.maximum_interval_ns,
            mean_interval_ns=(
                first.mean_interval_ns
                if first.positive_interval_count
                else None
            ),
            standard_deviation_ns=standard_deviation,
            p05_interval_ns=p05,
            p25_interval_ns=p25,
            median_interval_ns=median,
            p75_interval_ns=p75,
            p95_interval_ns=p95,
            p99_interval_ns=p99,
            jitter_p95_p05_ns=(
                p95 - p05
                if p95 is not None and p05 is not None
                else None
            ),
            jitter_rms_from_median_ns=(
                math.sqrt(median_square_sum / first.positive_interval_count)
                if first.positive_interval_count > 0 and median is not None
                else None
            ),
            coefficient_of_variation_percent=coefficient,
            nominal_frequency_hz=nominal_frequency,
            gap_threshold_ns=gap_threshold,
            gap_count=gap_count,
            percentile_sample_count=len(sample),
            gap_evidence=gap_evidence,
            warning=warning,
        ),
        consumed,
    )


def _compare_session(
    baseline: InterFrameSessionStatistics,
    current: InterFrameSessionStatistics,
) -> InterFrameSessionComparison:
    return InterFrameSessionComparison(
        session_id=current.session_id,
        session_name=current.session_name,
        baseline_session_id=baseline.session_id,
        mean_interval_delta_percent=_percent_change(
            current.mean_interval_ns,
            baseline.mean_interval_ns,
        ),
        median_interval_delta_percent=_percent_change(
            current.median_interval_ns,
            baseline.median_interval_ns,
        ),
        jitter_delta_percent=_percent_change(
            current.jitter_p95_p05_ns,
            baseline.jitter_p95_p05_ns,
        ),
        frequency_delta_percent=_percent_change(
            current.nominal_frequency_hz,
            baseline.nominal_frequency_hz,
        ),
        coefficient_of_variation_delta_percentage_points=_difference(
            current.coefficient_of_variation_percent,
            baseline.coefficient_of_variation_percent,
        ),
        gap_count_delta=current.gap_count - baseline.gap_count,
    )


def interframe_timing_result_to_payload(
    comparison_set: ComparisonSet,
    result: InterFrameTimingResult,
    *,
    records: tuple[SessionRecord, ...],
) -> dict[str, Any]:
    if tuple(item.session_id for item in result.sessions) != comparison_set.session_ids:
        raise ValueError("timing result sessions do not match comparison set order")
    if tuple(record.id for record in records) != comparison_set.session_ids:
        raise ValueError("session records do not match comparison set order")
    return {
        "schema": INTERFRAME_TIMING_SCHEMA,
        "schema_version": INTERFRAME_TIMING_SCHEMA_VERSION,
        "generated_by": {
            "provider_id": INTERFRAME_TIMING_PROVIDER_ID,
            "provider_version": INTERFRAME_TIMING_PROVIDER_VERSION,
            "algorithm_version": INTERFRAME_TIMING_ALGORITHM_VERSION,
            "crt_api": "1",
        },
        "comparison_set": {
            "id": comparison_set.id,
            "name": comparison_set.name,
            "session_ids": list(comparison_set.session_ids),
            "base_session_id": comparison_set.base_session_id,
        },
        "session_fingerprints": [
            {
                "session_id": record.id,
                "name": record.name,
                "frame_count": record.frame_count,
                "sha256": record.sha256,
            }
            for record in records
        ],
        "parameters": {
            "message_key": result.message_key,
            "gap_factor": result.gap_factor,
            "percentile_sample_limit": result.percentile_sample_limit,
            "maximum_gap_evidence_per_session": result.maximum_gap_evidence_per_session,
        },
        "baseline_session_id": result.baseline_session_id,
        "warnings": list(result.warnings),
        "sessions": [_session_to_payload(item) for item in result.sessions],
        "comparisons": [
            _comparison_to_payload(item)
            for item in result.comparisons
        ],
    }


def interframe_timing_result_from_payload(
    payload: Mapping[str, Any],
    *,
    comparison_set: ComparisonSet,
    records: tuple[SessionRecord, ...],
) -> InterFrameTimingResult:
    if str(payload.get("schema") or "") != INTERFRAME_TIMING_SCHEMA:
        raise ArtifactIntegrityError("unsupported inter-frame timing artifact schema")
    if int(payload.get("schema_version", 0)) != INTERFRAME_TIMING_SCHEMA_VERSION:
        raise ArtifactIntegrityError("unsupported inter-frame timing schema version")
    comparison_payload = _mapping(payload.get("comparison_set"), "comparison_set")
    if str(comparison_payload.get("id") or "") != comparison_set.id:
        raise StaleInterFrameTimingArtifact(
            "artifact belongs to another comparison set"
        )
    session_ids = tuple(
        str(item)
        for item in _sequence(comparison_payload.get("session_ids"))
    )
    if session_ids != comparison_set.session_ids:
        raise StaleInterFrameTimingArtifact("comparison set sessions changed")
    _validate_fingerprints(payload, records)
    parameters = _mapping(payload.get("parameters"), "parameters")
    message_key = format_timeline_message_key(
        parse_timeline_message_key(str(parameters.get("message_key") or ""))
    )
    sessions = tuple(
        _session_from_payload(item)
        for item in _sequence(payload.get("sessions"))
    )
    if tuple(item.session_id for item in sessions) != comparison_set.session_ids:
        raise StaleInterFrameTimingArtifact("artifact session order changed")
    comparisons = tuple(
        _comparison_from_payload(item)
        for item in _sequence(payload.get("comparisons", []))
    )
    baseline_id = str(payload.get("baseline_session_id") or "")
    if baseline_id not in comparison_set.session_ids:
        raise StaleInterFrameTimingArtifact("artifact baseline session changed")
    return InterFrameTimingResult(
        message_key=message_key,
        gap_factor=float(parameters.get("gap_factor", DEFAULT_GAP_FACTOR)),
        percentile_sample_limit=int(
            parameters.get(
                "percentile_sample_limit",
                DEFAULT_PERCENTILE_SAMPLE_LIMIT,
            )
        ),
        maximum_gap_evidence_per_session=int(
            parameters.get(
                "maximum_gap_evidence_per_session",
                DEFAULT_MAXIMUM_GAP_EVIDENCE,
            )
        ),
        baseline_session_id=baseline_id,
        sessions=sessions,
        comparisons=comparisons,
        warnings=tuple(
            str(item)
            for item in _sequence(payload.get("warnings", []))
        ),
    )


def _validate_fingerprints(
    payload: Mapping[str, Any],
    records: tuple[SessionRecord, ...],
) -> None:
    values = _sequence(payload.get("session_fingerprints"))
    if len(values) != len(records):
        raise StaleInterFrameTimingArtifact("session fingerprint count changed")
    for record, value in zip(records, values, strict=True):
        fingerprint = _mapping(value, "session fingerprint")
        if str(fingerprint.get("session_id") or "") != record.id:
            raise StaleInterFrameTimingArtifact("session order changed")
        if int(fingerprint.get("frame_count", -1)) != record.frame_count:
            raise StaleInterFrameTimingArtifact(
                f"session frame count changed: {record.name}"
            )
        saved_sha = str(fingerprint.get("sha256") or "")
        if saved_sha and record.sha256 and saved_sha != record.sha256:
            raise StaleInterFrameTimingArtifact(
                f"session SHA-256 changed: {record.name}"
            )


def _session_to_payload(item: InterFrameSessionStatistics) -> dict[str, Any]:
    return {
        "session_id": item.session_id,
        "session_name": item.session_name,
        "message_key": item.message_key,
        "occurrence_count": item.occurrence_count,
        "positive_interval_count": item.positive_interval_count,
        "non_positive_interval_count": item.non_positive_interval_count,
        "first_source_row": item.first_source_row,
        "last_source_row": item.last_source_row,
        "minimum_interval_ns": item.minimum_interval_ns,
        "maximum_interval_ns": item.maximum_interval_ns,
        "mean_interval_ns": item.mean_interval_ns,
        "standard_deviation_ns": item.standard_deviation_ns,
        "p05_interval_ns": item.p05_interval_ns,
        "p25_interval_ns": item.p25_interval_ns,
        "median_interval_ns": item.median_interval_ns,
        "p75_interval_ns": item.p75_interval_ns,
        "p95_interval_ns": item.p95_interval_ns,
        "p99_interval_ns": item.p99_interval_ns,
        "jitter_p95_p05_ns": item.jitter_p95_p05_ns,
        "jitter_rms_from_median_ns": item.jitter_rms_from_median_ns,
        "coefficient_of_variation_percent": item.coefficient_of_variation_percent,
        "nominal_frequency_hz": item.nominal_frequency_hz,
        "gap_threshold_ns": item.gap_threshold_ns,
        "gap_count": item.gap_count,
        "percentile_sample_count": item.percentile_sample_count,
        "warning": item.warning,
        "gap_evidence": [
            {
                "session_id": evidence.session_id,
                "session_name": evidence.session_name,
                "message_key": evidence.message_key,
                "previous_source_row": evidence.previous_source_row,
                "current_source_row": evidence.current_source_row,
                "previous_timestamp_ns": evidence.previous_timestamp_ns,
                "current_timestamp_ns": evidence.current_timestamp_ns,
                "interval_ns": evidence.interval_ns,
                "threshold_ns": evidence.threshold_ns,
                "ratio_to_nominal": evidence.ratio_to_nominal,
            }
            for evidence in item.gap_evidence
        ],
    }


def _session_from_payload(value: Any) -> InterFrameSessionStatistics:
    payload = _mapping(value, "session timing")
    evidence = tuple(
        _evidence_from_payload(item)
        for item in _sequence(payload.get("gap_evidence", []))
    )
    return InterFrameSessionStatistics(
        session_id=str(payload.get("session_id") or ""),
        session_name=str(payload.get("session_name") or ""),
        message_key=str(payload.get("message_key") or ""),
        occurrence_count=int(payload.get("occurrence_count", 0)),
        positive_interval_count=int(
            payload.get("positive_interval_count", 0)
        ),
        non_positive_interval_count=int(
            payload.get("non_positive_interval_count", 0)
        ),
        first_source_row=_optional_int(payload.get("first_source_row")),
        last_source_row=_optional_int(payload.get("last_source_row")),
        minimum_interval_ns=_optional_int(payload.get("minimum_interval_ns")),
        maximum_interval_ns=_optional_int(payload.get("maximum_interval_ns")),
        mean_interval_ns=_optional_float(payload.get("mean_interval_ns")),
        standard_deviation_ns=_optional_float(
            payload.get("standard_deviation_ns")
        ),
        p05_interval_ns=_optional_float(payload.get("p05_interval_ns")),
        p25_interval_ns=_optional_float(payload.get("p25_interval_ns")),
        median_interval_ns=_optional_float(payload.get("median_interval_ns")),
        p75_interval_ns=_optional_float(payload.get("p75_interval_ns")),
        p95_interval_ns=_optional_float(payload.get("p95_interval_ns")),
        p99_interval_ns=_optional_float(payload.get("p99_interval_ns")),
        jitter_p95_p05_ns=_optional_float(
            payload.get("jitter_p95_p05_ns")
        ),
        jitter_rms_from_median_ns=_optional_float(
            payload.get("jitter_rms_from_median_ns")
        ),
        coefficient_of_variation_percent=_optional_float(
            payload.get("coefficient_of_variation_percent")
        ),
        nominal_frequency_hz=_optional_float(
            payload.get("nominal_frequency_hz")
        ),
        gap_threshold_ns=_optional_float(payload.get("gap_threshold_ns")),
        gap_count=int(payload.get("gap_count", 0)),
        percentile_sample_count=int(
            payload.get("percentile_sample_count", 0)
        ),
        gap_evidence=evidence,
        warning=str(payload.get("warning") or ""),
    )


def _comparison_to_payload(
    item: InterFrameSessionComparison,
) -> dict[str, Any]:
    return {
        "session_id": item.session_id,
        "session_name": item.session_name,
        "baseline_session_id": item.baseline_session_id,
        "mean_interval_delta_percent": item.mean_interval_delta_percent,
        "median_interval_delta_percent": item.median_interval_delta_percent,
        "jitter_delta_percent": item.jitter_delta_percent,
        "frequency_delta_percent": item.frequency_delta_percent,
        "coefficient_of_variation_delta_percentage_points": (
            item.coefficient_of_variation_delta_percentage_points
        ),
        "gap_count_delta": item.gap_count_delta,
    }


def _comparison_from_payload(value: Any) -> InterFrameSessionComparison:
    payload = _mapping(value, "session comparison")
    return InterFrameSessionComparison(
        session_id=str(payload.get("session_id") or ""),
        session_name=str(payload.get("session_name") or ""),
        baseline_session_id=str(payload.get("baseline_session_id") or ""),
        mean_interval_delta_percent=_optional_float(
            payload.get("mean_interval_delta_percent")
        ),
        median_interval_delta_percent=_optional_float(
            payload.get("median_interval_delta_percent")
        ),
        jitter_delta_percent=_optional_float(
            payload.get("jitter_delta_percent")
        ),
        frequency_delta_percent=_optional_float(
            payload.get("frequency_delta_percent")
        ),
        coefficient_of_variation_delta_percentage_points=_optional_float(
            payload.get(
                "coefficient_of_variation_delta_percentage_points"
            )
        ),
        gap_count_delta=int(payload.get("gap_count_delta", 0)),
    )


def _evidence_from_payload(value: Any) -> InterFrameGapEvidence:
    payload = _mapping(value, "gap evidence")
    return InterFrameGapEvidence(
        session_id=str(payload.get("session_id") or ""),
        session_name=str(payload.get("session_name") or ""),
        message_key=str(payload.get("message_key") or ""),
        previous_source_row=int(payload.get("previous_source_row", -1)),
        current_source_row=int(payload.get("current_source_row", -1)),
        previous_timestamp_ns=int(payload.get("previous_timestamp_ns", 0)),
        current_timestamp_ns=int(payload.get("current_timestamp_ns", 0)),
        interval_ns=int(payload.get("interval_ns", 0)),
        threshold_ns=float(payload.get("threshold_ns", 0.0)),
        ratio_to_nominal=float(payload.get("ratio_to_nominal", 0.0)),
    )


def _records_for_comparison(
    project: CrtProject,
    comparison_set: ComparisonSet,
) -> tuple[SessionRecord, ...]:
    records = {record.id: record for record in project.list_sessions()}
    missing = [
        session_id
        for session_id in comparison_set.session_ids
        if session_id not in records
    ]
    if missing:
        raise KeyError(f"comparison sessions are missing: {missing}")
    return tuple(records[session_id] for session_id in comparison_set.session_ids)


def _frame_matches(frame, key) -> bool:
    if frame.channel != key.channel:
        return False
    if frame.arbitration_id != key.arbitration_id:
        return False
    if frame.is_extended_id != key.is_extended_id:
        return False
    if key.frame_kind == "error":
        return bool(frame.is_error_frame)
    if key.frame_kind == "remote":
        return bool(frame.is_remote_frame) and not frame.is_error_frame
    return not frame.is_remote_frame and not frame.is_error_frame


def _reservoir_add(
    sample: list[int],
    value: int,
    count: int,
    limit: int,
    seed: int,
) -> None:
    if len(sample) < limit:
        sample.append(value)
        return
    random_value = _splitmix64(seed ^ count)
    replacement = random_value % count
    if replacement < limit:
        sample[int(replacement)] = value


def _splitmix64(value: int) -> int:
    mask = (1 << 64) - 1
    value = (value + 0x9E3779B97F4A7C15) & mask
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
    return (value ^ (value >> 31)) & mask


def _percentile(values: Sequence[int], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * percentile / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _percent_change(
    current: float | None,
    baseline: float | None,
) -> float | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return (current - baseline) / baseline * 100.0


def _difference(
    current: float | None,
    baseline: float | None,
) -> float | None:
    if current is None or baseline is None:
        return None
    return current - baseline


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ArtifactIntegrityError(f"{label} must be an object")
    return value


def _sequence(value: Any) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise ArtifactIntegrityError("artifact value must be a sequence")
    return value


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _raise_if_cancelled(
    should_cancel: Callable[[], bool] | None,
) -> None:
    if should_cancel is not None and should_cancel():
        raise InterFrameTimingCancelled


__all__ = [
    "ComparisonInterFrameTimingService",
    "DEFAULT_GAP_FACTOR",
    "DEFAULT_MAXIMUM_GAP_EVIDENCE",
    "DEFAULT_PERCENTILE_SAMPLE_LIMIT",
    "INTERFRAME_TIMING_ARTIFACT_TYPE",
    "INTERFRAME_TIMING_SCHEMA",
    "InterFrameGapEvidence",
    "InterFrameSessionComparison",
    "InterFrameSessionStatistics",
    "InterFrameTimingCancelled",
    "InterFrameTimingExecutionResult",
    "InterFrameTimingResult",
    "StaleInterFrameTimingArtifact",
    "StoredInterFrameTiming",
    "analyze_comparison_interframe_timing",
    "interframe_timing_result_from_payload",
    "interframe_timing_result_to_payload",
]
