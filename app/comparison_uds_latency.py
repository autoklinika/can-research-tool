from __future__ import annotations

import hashlib
import heapq
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .artifact_catalog import ArtifactCatalog, ArtifactIntegrityError
from .comparison_timeline import format_timeline_message_key, parse_timeline_message_key
from .domain import AnalysisInput, AnalysisStatus, Artifact, ArtifactSource, ComparisonSet
from .extensions import ArtifactWriter, CancellationToken, ExtensionCancelled
from .message_models import TransportMessage
from .project import CrtProject, SessionRecord
from .project_domain_store import ProjectDomainStore
from .protocol_catalog import (
    UDS_SERVICE_NAMES,
    UDS_SUBFUNCTION_SERVICES,
    uds_nrc_name,
    uds_service_name,
)
from .session_stream import SessionPagedReader
from .transport import IsoTpReassembler

UDS_LATENCY_ARTIFACT_TYPE = "comparison_uds_latency"
UDS_LATENCY_SCHEMA = "crt.comparison_uds_latency"
UDS_LATENCY_SCHEMA_VERSION = 1
UDS_LATENCY_PROVIDER_ID = "crt.comparison.uds_latency"
UDS_LATENCY_PROVIDER_VERSION = "1.0.0"
UDS_LATENCY_ALGORITHM_VERSION = "1"
DEFAULT_TIMEOUT_MS = 5_000.0
DEFAULT_PERCENTILE_SAMPLE_LIMIT = 100_000
DEFAULT_MAXIMUM_TRANSACTION_EVIDENCE = 2_000
DEFAULT_MAXIMUM_PENDING_EVIDENCE = 16
DEFAULT_MAXIMUM_UNMATCHED_EVIDENCE = 100
_MAXIMUM_ARTIFACT_BYTES = 256 * 1024 * 1024
_CANCEL_STRIDE = 1_024


class UdsLatencyCancelled(RuntimeError):
    """Raised when passive UDS latency analysis is cancelled."""


class StaleUdsLatencyArtifact(ArtifactIntegrityError):
    """Raised when a saved UDS latency artifact no longer matches its sessions."""


@dataclass(frozen=True, slots=True)
class UdsLatencyConfiguration:
    request_message_key: str
    response_message_key: str
    timeout_ms: float = DEFAULT_TIMEOUT_MS
    percentile_sample_limit: int = DEFAULT_PERCENTILE_SAMPLE_LIMIT
    maximum_transaction_evidence_per_session: int = (
        DEFAULT_MAXIMUM_TRANSACTION_EVIDENCE
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_message_key": self.request_message_key,
            "response_message_key": self.response_message_key,
            "timeout_ms": self.timeout_ms,
            "percentile_sample_limit": self.percentile_sample_limit,
            "maximum_transaction_evidence_per_session": (
                self.maximum_transaction_evidence_per_session
            ),
        }


@dataclass(frozen=True, slots=True)
class UdsMessageEvidence:
    session_id: str
    session_name: str
    message_key: str
    first_source_row: int
    last_source_row: int
    first_timestamp_ns: int
    last_timestamp_ns: int
    frame_count: int
    payload_hex: str
    service_id: int | None
    service_name: str
    requested_service_id: int | None
    negative_response_code: int | None
    negative_response_name: str
    response_pending: bool
    complete: bool
    error: str = ""


@dataclass(frozen=True, slots=True)
class UdsTransactionEvidence:
    session_id: str
    session_name: str
    request_service_id: int
    request_service_name: str
    status: str
    request: UdsMessageEvidence
    first_response: UdsMessageEvidence | None
    final_response: UdsMessageEvidence | None
    pending_responses: tuple[UdsMessageEvidence, ...]
    response_pending_count: int
    first_response_latency_ns: int | None
    final_response_latency_ns: int | None
    final_negative_response_code: int | None
    suppress_positive_response: bool


@dataclass(frozen=True, slots=True)
class UdsSessionLatencyStatistics:
    session_id: str
    session_name: str
    request_message_key: str
    response_message_key: str
    request_count: int
    completed_count: int
    positive_response_count: int
    negative_response_count: int
    timeout_count: int
    capture_ended_count: int
    suppressed_no_response_count: int
    response_pending_transaction_count: int
    response_pending_count: int
    unmatched_response_count: int
    incomplete_isotp_message_count: int
    completion_rate_percent: float | None
    mean_first_response_latency_ns: float | None
    p50_first_response_latency_ns: float | None
    p95_first_response_latency_ns: float | None
    p99_first_response_latency_ns: float | None
    mean_final_response_latency_ns: float | None
    p50_final_response_latency_ns: float | None
    p95_final_response_latency_ns: float | None
    p99_final_response_latency_ns: float | None
    first_latency_sample_count: int
    final_latency_sample_count: int
    transaction_evidence: tuple[UdsTransactionEvidence, ...]
    unmatched_responses: tuple[UdsMessageEvidence, ...]
    evidence_truncated: bool
    warning: str = ""


@dataclass(frozen=True, slots=True)
class UdsSessionLatencyComparison:
    session_id: str
    session_name: str
    baseline_session_id: str
    completion_rate_delta_percentage_points: float | None
    p50_first_latency_delta_percent: float | None
    p50_final_latency_delta_percent: float | None
    p95_final_latency_delta_percent: float | None
    timeout_count_delta: int
    negative_response_count_delta: int
    response_pending_count_delta: int
    unmatched_response_count_delta: int


@dataclass(frozen=True, slots=True)
class UdsLatencyResult:
    configuration: UdsLatencyConfiguration
    baseline_session_id: str
    sessions: tuple[UdsSessionLatencyStatistics, ...]
    comparisons: tuple[UdsSessionLatencyComparison, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UdsLatencyExecutionResult:
    result: UdsLatencyResult
    artifact: Artifact


@dataclass(frozen=True, slots=True)
class StoredUdsLatency:
    artifact: Artifact
    result: UdsLatencyResult


@dataclass(slots=True)
class _OpenRequest:
    request: UdsMessageEvidence
    service_id: int
    service_name: str
    suppress_positive_response: bool
    deadline_reference_ns: int
    first_response: UdsMessageEvidence | None = None
    pending_responses: list[UdsMessageEvidence] = field(default_factory=list)
    response_pending_count: int = 0


@dataclass(slots=True)
class _LatencyAccumulator:
    sample_limit: int
    seed: int
    count: int = 0
    total: int = 0
    sample: list[int] = field(default_factory=list)

    def add(self, value: int) -> None:
        if value < 0:
            return
        self.count += 1
        self.total += value
        _reservoir_add(
            self.sample,
            value,
            self.count,
            self.sample_limit,
            self.seed,
        )


@dataclass(slots=True)
class _SessionState:
    request_count: int = 0
    completed_count: int = 0
    positive_response_count: int = 0
    negative_response_count: int = 0
    timeout_count: int = 0
    capture_ended_count: int = 0
    suppressed_no_response_count: int = 0
    response_pending_transaction_count: int = 0
    response_pending_count: int = 0
    unmatched_response_count: int = 0
    incomplete_isotp_message_count: int = 0
    serial: int = 0
    evidence_heap: list[tuple[int, int, int, UdsTransactionEvidence]] = field(
        default_factory=list
    )
    unmatched_responses: list[UdsMessageEvidence] = field(default_factory=list)
    evidence_truncated: bool = False


class ComparisonUdsLatencyService:
    """Passive request/response pairing and UDS latency artifact service."""

    def __init__(self, project: CrtProject) -> None:
        self.project = project
        self.store = ProjectDomainStore(project)
        self.catalog = ArtifactCatalog(project)

    def run_and_save(
        self,
        comparison_set: ComparisonSet,
        request_message_key: str,
        response_message_key: str,
        *,
        timeout_ms: float = DEFAULT_TIMEOUT_MS,
        percentile_sample_limit: int = DEFAULT_PERCENTILE_SAMPLE_LIMIT,
        maximum_transaction_evidence_per_session: int = (
            DEFAULT_MAXIMUM_TRANSACTION_EVIDENCE
        ),
        cancellation: CancellationToken | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> UdsLatencyExecutionResult:
        token = cancellation or CancellationToken()
        configuration = normalize_uds_latency_configuration(
            request_message_key=request_message_key,
            response_message_key=response_message_key,
            timeout_ms=timeout_ms,
            percentile_sample_limit=percentile_sample_limit,
            maximum_transaction_evidence_per_session=(
                maximum_transaction_evidence_per_session
            ),
        )
        parameters = configuration.to_dict()
        analysis_input = AnalysisInput(
            kind="comparison_set",
            source_id=comparison_set.id,
            parameters=parameters,
        )
        run = self.store.create_analysis_run(
            provider_id=UDS_LATENCY_PROVIDER_ID,
            provider_version=UDS_LATENCY_PROVIDER_VERSION,
            algorithm_version=UDS_LATENCY_ALGORITHM_VERSION,
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
            result = analyze_comparison_uds_latency(
                self.project,
                comparison_set,
                configuration,
                should_cancel=lambda: token.is_cancelled,
                progress_callback=progress_callback,
            )
            records = _records_for_comparison(self.project, comparison_set)
            artifact = writer.write_json(
                filename="comparison-uds-latency.json",
                artifact_type=UDS_LATENCY_ARTIFACT_TYPE,
                schema_version=UDS_LATENCY_SCHEMA_VERSION,
                sources=tuple(
                    ArtifactSource(
                        session_id=record.id,
                        source_kind="session",
                        source_reference={
                            "comparison_set_id": comparison_set.id,
                            "role": (
                                "base"
                                if record.id == result.baseline_session_id
                                else "compared"
                            ),
                            "frame_count": record.frame_count,
                            "sha256": record.sha256,
                            "request_message_key": (
                                configuration.request_message_key
                            ),
                            "response_message_key": (
                                configuration.response_message_key
                            ),
                        },
                    )
                    for record in records
                ),
                payload=uds_latency_result_to_payload(
                    comparison_set,
                    result,
                    records=records,
                ),
                metadata={
                    "comparison_set_id": comparison_set.id,
                    "request_message_key": configuration.request_message_key,
                    "response_message_key": configuration.response_message_key,
                    "session_count": len(result.sessions),
                    "request_count": sum(
                        item.request_count for item in result.sessions
                    ),
                    "timeout_count": sum(
                        item.timeout_count for item in result.sessions
                    ),
                    "warning_count": len(result.warnings),
                },
            )
        except (UdsLatencyCancelled, ExtensionCancelled):
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
        return UdsLatencyExecutionResult(result=result, artifact=artifact)

    def load_latest_compatible(
        self,
        comparison_set: ComparisonSet,
        *,
        request_message_key: str = "",
        response_message_key: str = "",
        should_cancel: Callable[[], bool] | None = None,
    ) -> StoredUdsLatency | None:
        normalized_request = _optional_normalized_key(request_message_key)
        normalized_response = _optional_normalized_key(response_message_key)
        records = _records_for_comparison(self.project, comparison_set)
        for artifact in self.catalog.list_for_comparison_set(comparison_set.id):
            _raise_if_cancelled(should_cancel)
            if artifact.artifact_type != UDS_LATENCY_ARTIFACT_TYPE:
                continue
            if normalized_request and str(
                artifact.metadata.get("request_message_key") or ""
            ) != normalized_request:
                continue
            if normalized_response and str(
                artifact.metadata.get("response_message_key") or ""
            ) != normalized_response:
                continue
            try:
                payload = self.catalog.read_json(
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
            return StoredUdsLatency(artifact=artifact, result=result)
        return None


def normalize_uds_latency_configuration(
    *,
    request_message_key: str,
    response_message_key: str,
    timeout_ms: float = DEFAULT_TIMEOUT_MS,
    percentile_sample_limit: int = DEFAULT_PERCENTILE_SAMPLE_LIMIT,
    maximum_transaction_evidence_per_session: int = (
        DEFAULT_MAXIMUM_TRANSACTION_EVIDENCE
    ),
) -> UdsLatencyConfiguration:
    request_key = format_timeline_message_key(
        parse_timeline_message_key(request_message_key)
    )
    response_key = format_timeline_message_key(
        parse_timeline_message_key(response_message_key)
    )
    if request_key == response_key:
        raise ValueError("Klucz żądania i odpowiedzi muszą być różne.")
    request_parsed = parse_timeline_message_key(request_key)
    response_parsed = parse_timeline_message_key(response_key)
    if request_parsed.frame_kind != "data" or response_parsed.frame_kind != "data":
        raise ValueError("Analiza UDS wymaga ramek typu data.")
    timeout = float(timeout_ms)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_ms must be a finite value greater than zero")
    sample_limit = int(percentile_sample_limit)
    if sample_limit < 128:
        raise ValueError("percentile_sample_limit must be at least 128")
    evidence_limit = int(maximum_transaction_evidence_per_session)
    if evidence_limit <= 0:
        raise ValueError(
            "maximum_transaction_evidence_per_session must be greater than zero"
        )
    return UdsLatencyConfiguration(
        request_message_key=request_key,
        response_message_key=response_key,
        timeout_ms=timeout,
        percentile_sample_limit=sample_limit,
        maximum_transaction_evidence_per_session=evidence_limit,
    )


def analyze_comparison_uds_latency(
    project: CrtProject,
    comparison_set: ComparisonSet,
    configuration: UdsLatencyConfiguration,
    *,
    should_cancel: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> UdsLatencyResult:
    configuration = normalize_uds_latency_configuration(
        **configuration.to_dict()
    )
    records = _records_for_comparison(project, comparison_set)
    total_work = max(1, sum(max(0, record.frame_count) for record in records))
    progress = 0
    sessions: list[UdsSessionLatencyStatistics] = []
    warnings: list[str] = []
    for record in records:
        _raise_if_cancelled(should_cancel)
        statistics, consumed = _analyze_session(
            project,
            record,
            configuration,
            should_cancel=should_cancel,
            progress_callback=progress_callback,
            progress_offset=progress,
            total_work=total_work,
        )
        progress += consumed
        sessions.append(statistics)
        if statistics.warning:
            warnings.append(statistics.warning)
    baseline_id = comparison_set.base_session_id or comparison_set.session_ids[0]
    baseline = next(item for item in sessions if item.session_id == baseline_id)
    comparisons = tuple(
        _compare_session(baseline, item)
        for item in sessions
        if item.session_id != baseline_id
    )
    if progress_callback is not None:
        progress_callback(total_work, total_work, "Zapisuję wynik latencji UDS")
    return UdsLatencyResult(
        configuration=configuration,
        baseline_session_id=baseline_id,
        sessions=tuple(sessions),
        comparisons=comparisons,
        warnings=tuple(warnings),
    )


def _analyze_session(
    project: CrtProject,
    record: SessionRecord,
    configuration: UdsLatencyConfiguration,
    *,
    should_cancel: Callable[[], bool] | None,
    progress_callback: Callable[[int, int, str], None] | None,
    progress_offset: int,
    total_work: int,
) -> tuple[UdsSessionLatencyStatistics, int]:
    timeout_ns = int(configuration.timeout_ms * 1_000_000.0)
    seed_material = (
        f"{record.id}|{configuration.request_message_key}|"
        f"{configuration.response_message_key}"
    ).encode("utf-8")
    seed = int.from_bytes(
        hashlib.blake2b(seed_material, digest_size=8).digest(),
        "big",
    )
    first_latency = _LatencyAccumulator(
        sample_limit=configuration.percentile_sample_limit,
        seed=seed ^ 0x13579BDF,
    )
    final_latency = _LatencyAccumulator(
        sample_limit=configuration.percentile_sample_limit,
        seed=seed ^ 0x2468ACE0,
    )
    state = _SessionState()
    open_requests: list[_OpenRequest] = []
    last_capture_timestamp_ns = 0
    consumed = 0

    for role, evidence, source_row in _iter_uds_messages(
        project,
        record,
        configuration,
        should_cancel=should_cancel,
    ):
        consumed = max(consumed, source_row + 1)
        last_capture_timestamp_ns = max(
            last_capture_timestamp_ns,
            evidence.last_timestamp_ns,
        )
        if source_row % _CANCEL_STRIDE == 0:
            _raise_if_cancelled(should_cancel)
            if progress_callback is not None:
                progress_callback(
                    min(total_work, progress_offset + source_row + 1),
                    total_work,
                    f"Paruję UDS: {record.name}",
                )
        _expire_requests(
            open_requests,
            evidence.first_timestamp_ns,
            timeout_ns,
            state,
            first_latency,
            final_latency,
            configuration.maximum_transaction_evidence_per_session,
        )
        if not evidence.complete:
            state.incomplete_isotp_message_count += 1
            continue
        if role == "request":
            service_id = evidence.service_id
            if service_id is None or service_id not in UDS_SERVICE_NAMES:
                continue
            state.request_count += 1
            suppress = _suppress_positive_response(evidence)
            open_requests.append(
                _OpenRequest(
                    request=evidence,
                    service_id=service_id,
                    service_name=uds_service_name(service_id),
                    suppress_positive_response=suppress,
                    deadline_reference_ns=evidence.last_timestamp_ns,
                )
            )
            continue

        base_service_id = _response_base_service_id(evidence)
        if base_service_id is None:
            _record_unmatched_response(state, evidence)
            continue
        match_index = _find_matching_request(
            open_requests,
            base_service_id,
            evidence.first_timestamp_ns,
        )
        if match_index is None:
            _record_unmatched_response(state, evidence)
            continue
        pending = evidence.response_pending
        current = open_requests[match_index]
        if current.first_response is None:
            current.first_response = evidence
        if pending:
            current.response_pending_count += 1
            state.response_pending_count += 1
            if len(current.pending_responses) < DEFAULT_MAXIMUM_PENDING_EVIDENCE:
                current.pending_responses.append(evidence)
            current.deadline_reference_ns = evidence.first_timestamp_ns
            continue

        open_requests.pop(match_index)
        status = (
            "negative-response"
            if evidence.negative_response_code is not None
            else "positive-response"
        )
        _finalize_request(
            current,
            status=status,
            final_response=evidence,
            state=state,
            first_latency=first_latency,
            final_latency=final_latency,
            maximum_evidence=(
                configuration.maximum_transaction_evidence_per_session
            ),
        )

    reader = SessionPagedReader(project.absolute_path(record.relative_path))
    consumed = reader.frame_count
    if reader.frame_count:
        final_page = reader.read_page(reader.frame_count - 1, 1)
        if final_page:
            last_capture_timestamp_ns = int(final_page[0].timestamp_ns)

    for current in open_requests:
        if current.suppress_positive_response and current.first_response is None:
            status = "suppressed-no-response"
        elif (
            last_capture_timestamp_ns - current.deadline_reference_ns
            >= timeout_ns
        ):
            status = "timeout"
        else:
            status = "capture-ended"
        _finalize_request(
            current,
            status=status,
            final_response=None,
            state=state,
            first_latency=first_latency,
            final_latency=final_latency,
            maximum_evidence=(
                configuration.maximum_transaction_evidence_per_session
            ),
        )

    transaction_evidence = tuple(
        item[3]
        for item in sorted(
            state.evidence_heap,
            key=lambda value: (
                value[3].request.first_timestamp_ns,
                value[3].request.first_source_row,
            ),
        )
    )
    first_sample = sorted(first_latency.sample)
    final_sample = sorted(final_latency.sample)
    warning_parts: list[str] = []
    if state.request_count == 0:
        warning_parts.append(
            f"Sesja {record.name!r} nie zawiera kompletnych żądań UDS "
            f"dla {configuration.request_message_key}."
        )
    if state.unmatched_response_count:
        warning_parts.append(
            f"nieparowane odpowiedzi: {state.unmatched_response_count}"
        )
    if state.incomplete_isotp_message_count:
        warning_parts.append(
            f"niekompletne komunikaty ISO-TP: "
            f"{state.incomplete_isotp_message_count}"
        )
    warning = "; ".join(warning_parts)
    return (
        UdsSessionLatencyStatistics(
            session_id=record.id,
            session_name=record.name,
            request_message_key=configuration.request_message_key,
            response_message_key=configuration.response_message_key,
            request_count=state.request_count,
            completed_count=state.completed_count,
            positive_response_count=state.positive_response_count,
            negative_response_count=state.negative_response_count,
            timeout_count=state.timeout_count,
            capture_ended_count=state.capture_ended_count,
            suppressed_no_response_count=state.suppressed_no_response_count,
            response_pending_transaction_count=(
                state.response_pending_transaction_count
            ),
            response_pending_count=state.response_pending_count,
            unmatched_response_count=state.unmatched_response_count,
            incomplete_isotp_message_count=(
                state.incomplete_isotp_message_count
            ),
            completion_rate_percent=(
                state.completed_count / state.request_count * 100.0
                if state.request_count
                else None
            ),
            mean_first_response_latency_ns=(
                first_latency.total / first_latency.count
                if first_latency.count
                else None
            ),
            p50_first_response_latency_ns=_percentile(first_sample, 50),
            p95_first_response_latency_ns=_percentile(first_sample, 95),
            p99_first_response_latency_ns=_percentile(first_sample, 99),
            mean_final_response_latency_ns=(
                final_latency.total / final_latency.count
                if final_latency.count
                else None
            ),
            p50_final_response_latency_ns=_percentile(final_sample, 50),
            p95_final_response_latency_ns=_percentile(final_sample, 95),
            p99_final_response_latency_ns=_percentile(final_sample, 99),
            first_latency_sample_count=len(first_sample),
            final_latency_sample_count=len(final_sample),
            transaction_evidence=transaction_evidence,
            unmatched_responses=tuple(state.unmatched_responses),
            evidence_truncated=state.evidence_truncated,
            warning=warning,
        ),
        consumed,
    )


def _iter_uds_messages(
    project: CrtProject,
    record: SessionRecord,
    configuration: UdsLatencyConfiguration,
    *,
    should_cancel: Callable[[], bool] | None,
):
    request_key = parse_timeline_message_key(
        configuration.request_message_key
    )
    response_key = parse_timeline_message_key(
        configuration.response_message_key
    )
    request_reassembler = IsoTpReassembler()
    response_reassembler = IsoTpReassembler()
    source_rows: dict[int, int] = {}
    reader = SessionPagedReader(project.absolute_path(record.relative_path))
    last_row = -1
    for source_row, frame in enumerate(reader.iter_frames()):
        last_row = source_row
        if source_row % _CANCEL_STRIDE == 0:
            _raise_if_cancelled(should_cancel)
        role = ""
        reassembler: IsoTpReassembler | None = None
        message_key = ""
        if _frame_matches(frame, request_key):
            role = "request"
            reassembler = request_reassembler
            message_key = configuration.request_message_key
        elif _frame_matches(frame, response_key):
            role = "response"
            reassembler = response_reassembler
            message_key = configuration.response_message_key
        if reassembler is None or not reassembler.accepts(frame):
            continue
        pci_type = frame.data[0] >> 4 if frame.data else -1
        if pci_type != 3:
            source_rows[int(frame.sequence)] = source_row
        for message in reassembler.feed(frame):
            evidence = _message_evidence(
                record,
                message_key,
                message,
                source_rows,
            )
            if evidence is not None:
                yield role, evidence, source_row
    for role, key, reassembler in (
        (
            "request",
            configuration.request_message_key,
            request_reassembler,
        ),
        (
            "response",
            configuration.response_message_key,
            response_reassembler,
        ),
    ):
        for message in reassembler.flush():
            evidence = _message_evidence(record, key, message, source_rows)
            if evidence is not None:
                yield role, evidence, max(0, last_row)
    _raise_if_cancelled(should_cancel)


def _message_evidence(
    record: SessionRecord,
    message_key: str,
    message: TransportMessage,
    source_rows: dict[int, int],
) -> UdsMessageEvidence | None:
    rows = [
        source_rows.pop(int(sequence), None)
        for sequence in message.frame_sequences
    ]
    valid_rows = [int(value) for value in rows if value is not None]
    if not valid_rows:
        return None
    payload = bytes(message.payload)
    service_id = payload[0] if payload else None
    requested_service_id = (
        payload[1]
        if len(payload) >= 2 and service_id == 0x7F
        else None
    )
    nrc = (
        payload[2]
        if len(payload) >= 3 and service_id == 0x7F
        else None
    )
    base_service = (
        requested_service_id
        if requested_service_id is not None
        else (
            service_id - 0x40
            if service_id is not None
            and service_id - 0x40 in UDS_SERVICE_NAMES
            else service_id
        )
    )
    return UdsMessageEvidence(
        session_id=record.id,
        session_name=record.name,
        message_key=message_key,
        first_source_row=min(valid_rows),
        last_source_row=max(valid_rows),
        first_timestamp_ns=int(message.first_timestamp_ns),
        last_timestamp_ns=int(message.last_timestamp_ns),
        frame_count=int(message.frame_count),
        payload_hex=message.payload_hex,
        service_id=service_id,
        service_name=uds_service_name(base_service),
        requested_service_id=requested_service_id,
        negative_response_code=nrc,
        negative_response_name=(uds_nrc_name(nrc) if nrc is not None else ""),
        response_pending=nrc == 0x78,
        complete=bool(message.complete),
        error=str(message.error or ""),
    )


def _suppress_positive_response(evidence: UdsMessageEvidence) -> bool:
    if evidence.service_id not in UDS_SUBFUNCTION_SERVICES:
        return False
    payload = _payload_bytes(evidence.payload_hex)
    return len(payload) >= 2 and bool(payload[1] & 0x80)


def _payload_bytes(value: str) -> bytes:
    text = str(value).replace(" ", "")
    try:
        return bytes.fromhex(text)
    except ValueError:
        return b""


def _response_base_service_id(
    evidence: UdsMessageEvidence,
) -> int | None:
    if evidence.negative_response_code is not None:
        return evidence.requested_service_id
    if evidence.service_id is None:
        return None
    candidate = evidence.service_id - 0x40
    return candidate if candidate in UDS_SERVICE_NAMES else None


def _find_matching_request(
    open_requests: list[_OpenRequest],
    service_id: int,
    response_timestamp_ns: int,
) -> int | None:
    for index, current in enumerate(open_requests):
        if current.service_id != service_id:
            continue
        if response_timestamp_ns < current.request.last_timestamp_ns:
            continue
        return index
    return None


def _expire_requests(
    open_requests: list[_OpenRequest],
    current_timestamp_ns: int,
    timeout_ns: int,
    state: _SessionState,
    first_latency: _LatencyAccumulator,
    final_latency: _LatencyAccumulator,
    maximum_evidence: int,
) -> None:
    retained: list[_OpenRequest] = []
    for current in open_requests:
        if current_timestamp_ns - current.deadline_reference_ns < timeout_ns:
            retained.append(current)
            continue
        status = (
            "suppressed-no-response"
            if current.suppress_positive_response
            and current.first_response is None
            else "timeout"
        )
        _finalize_request(
            current,
            status=status,
            final_response=None,
            state=state,
            first_latency=first_latency,
            final_latency=final_latency,
            maximum_evidence=maximum_evidence,
        )
    open_requests[:] = retained


def _finalize_request(
    current: _OpenRequest,
    *,
    status: str,
    final_response: UdsMessageEvidence | None,
    state: _SessionState,
    first_latency: _LatencyAccumulator,
    final_latency: _LatencyAccumulator,
    maximum_evidence: int,
) -> None:
    first_value = _latency_ns(current.request, current.first_response)
    final_value = _latency_ns(current.request, final_response)
    if first_value is not None:
        first_latency.add(first_value)
    if final_value is not None:
        final_latency.add(final_value)
    if status == "positive-response":
        state.completed_count += 1
        state.positive_response_count += 1
    elif status == "negative-response":
        state.completed_count += 1
        state.negative_response_count += 1
    elif status == "timeout":
        state.timeout_count += 1
    elif status == "capture-ended":
        state.capture_ended_count += 1
    elif status == "suppressed-no-response":
        state.suppressed_no_response_count += 1
    if current.response_pending_count:
        state.response_pending_transaction_count += 1
    transaction = UdsTransactionEvidence(
        session_id=current.request.session_id,
        session_name=current.request.session_name,
        request_service_id=current.service_id,
        request_service_name=current.service_name,
        status=status,
        request=current.request,
        first_response=current.first_response,
        final_response=final_response,
        pending_responses=tuple(current.pending_responses),
        response_pending_count=current.response_pending_count,
        first_response_latency_ns=first_value,
        final_response_latency_ns=final_value,
        final_negative_response_code=(
            final_response.negative_response_code
            if final_response is not None
            else None
        ),
        suppress_positive_response=current.suppress_positive_response,
    )
    _retain_transaction(state, transaction, maximum_evidence)


def _latency_ns(
    request: UdsMessageEvidence,
    response: UdsMessageEvidence | None,
) -> int | None:
    if response is None:
        return None
    value = response.first_timestamp_ns - request.last_timestamp_ns
    return value if value >= 0 else None


def _retain_transaction(
    state: _SessionState,
    transaction: UdsTransactionEvidence,
    maximum_evidence: int,
) -> None:
    priority = {
        "timeout": 6,
        "capture-ended": 5,
        "negative-response": 4,
        "positive-response": 2,
        "suppressed-no-response": 1,
    }.get(transaction.status, 0)
    if transaction.response_pending_count:
        priority += 1
    latency = (
        transaction.final_response_latency_ns
        if transaction.final_response_latency_ns is not None
        else transaction.first_response_latency_ns or 0
    )
    state.serial += 1
    item = (priority, int(latency), state.serial, transaction)
    if len(state.evidence_heap) < maximum_evidence:
        heapq.heappush(state.evidence_heap, item)
        return
    state.evidence_truncated = True
    if item[:3] > state.evidence_heap[0][:3]:
        heapq.heapreplace(state.evidence_heap, item)


def _record_unmatched_response(
    state: _SessionState,
    evidence: UdsMessageEvidence,
) -> None:
    state.unmatched_response_count += 1
    if len(state.unmatched_responses) < DEFAULT_MAXIMUM_UNMATCHED_EVIDENCE:
        state.unmatched_responses.append(evidence)


def _compare_session(
    baseline: UdsSessionLatencyStatistics,
    current: UdsSessionLatencyStatistics,
) -> UdsSessionLatencyComparison:
    return UdsSessionLatencyComparison(
        session_id=current.session_id,
        session_name=current.session_name,
        baseline_session_id=baseline.session_id,
        completion_rate_delta_percentage_points=_difference(
            current.completion_rate_percent,
            baseline.completion_rate_percent,
        ),
        p50_first_latency_delta_percent=_percent_change(
            current.p50_first_response_latency_ns,
            baseline.p50_first_response_latency_ns,
        ),
        p50_final_latency_delta_percent=_percent_change(
            current.p50_final_response_latency_ns,
            baseline.p50_final_response_latency_ns,
        ),
        p95_final_latency_delta_percent=_percent_change(
            current.p95_final_response_latency_ns,
            baseline.p95_final_response_latency_ns,
        ),
        timeout_count_delta=current.timeout_count - baseline.timeout_count,
        negative_response_count_delta=(
            current.negative_response_count - baseline.negative_response_count
        ),
        response_pending_count_delta=(
            current.response_pending_count - baseline.response_pending_count
        ),
        unmatched_response_count_delta=(
            current.unmatched_response_count - baseline.unmatched_response_count
        ),
    )


def uds_latency_result_to_payload(
    comparison_set: ComparisonSet,
    result: UdsLatencyResult,
    *,
    records: tuple[SessionRecord, ...],
) -> dict[str, Any]:
    if tuple(item.session_id for item in result.sessions) != comparison_set.session_ids:
        raise ValueError("UDS latency result sessions do not match comparison set order")
    if tuple(record.id for record in records) != comparison_set.session_ids:
        raise ValueError("session records do not match comparison set order")
    return {
        "schema": UDS_LATENCY_SCHEMA,
        "schema_version": UDS_LATENCY_SCHEMA_VERSION,
        "generated_by": {
            "provider_id": UDS_LATENCY_PROVIDER_ID,
            "provider_version": UDS_LATENCY_PROVIDER_VERSION,
            "algorithm_version": UDS_LATENCY_ALGORITHM_VERSION,
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
        "configuration": result.configuration.to_dict(),
        "baseline_session_id": result.baseline_session_id,
        "warnings": list(result.warnings),
        "sessions": [_session_to_payload(item) for item in result.sessions],
        "comparisons": [
            _comparison_to_payload(item) for item in result.comparisons
        ],
    }


def uds_latency_result_from_payload(
    payload: Mapping[str, Any],
    *,
    comparison_set: ComparisonSet,
    records: tuple[SessionRecord, ...],
) -> UdsLatencyResult:
    if str(payload.get("schema") or "") != UDS_LATENCY_SCHEMA:
        raise ArtifactIntegrityError("unsupported UDS latency artifact schema")
    if int(payload.get("schema_version", 0)) != UDS_LATENCY_SCHEMA_VERSION:
        raise ArtifactIntegrityError("unsupported UDS latency schema version")
    comparison_payload = _mapping(payload.get("comparison_set"), "comparison_set")
    if str(comparison_payload.get("id") or "") != comparison_set.id:
        raise StaleUdsLatencyArtifact("artifact belongs to another comparison set")
    session_ids = tuple(
        str(item) for item in _sequence(comparison_payload.get("session_ids"))
    )
    if session_ids != comparison_set.session_ids:
        raise StaleUdsLatencyArtifact("comparison set sessions changed")
    _validate_fingerprints(payload, records)
    configuration_payload = _mapping(
        payload.get("configuration"),
        "configuration",
    )
    configuration = normalize_uds_latency_configuration(
        request_message_key=str(
            configuration_payload.get("request_message_key") or ""
        ),
        response_message_key=str(
            configuration_payload.get("response_message_key") or ""
        ),
        timeout_ms=float(
            configuration_payload.get("timeout_ms", DEFAULT_TIMEOUT_MS)
        ),
        percentile_sample_limit=int(
            configuration_payload.get(
                "percentile_sample_limit",
                DEFAULT_PERCENTILE_SAMPLE_LIMIT,
            )
        ),
        maximum_transaction_evidence_per_session=int(
            configuration_payload.get(
                "maximum_transaction_evidence_per_session",
                DEFAULT_MAXIMUM_TRANSACTION_EVIDENCE,
            )
        ),
    )
    sessions = tuple(
        _session_from_payload(item)
        for item in _sequence(payload.get("sessions"))
    )
    if tuple(item.session_id for item in sessions) != comparison_set.session_ids:
        raise StaleUdsLatencyArtifact("artifact session order changed")
    baseline_id = str(payload.get("baseline_session_id") or "")
    if baseline_id not in comparison_set.session_ids:
        raise StaleUdsLatencyArtifact("artifact baseline session changed")
    comparisons = tuple(
        _comparison_from_payload(item)
        for item in _sequence(payload.get("comparisons", []))
    )
    return UdsLatencyResult(
        configuration=configuration,
        baseline_session_id=baseline_id,
        sessions=sessions,
        comparisons=comparisons,
        warnings=tuple(
            str(item) for item in _sequence(payload.get("warnings", []))
        ),
    )


def _session_to_payload(item: UdsSessionLatencyStatistics) -> dict[str, Any]:
    return {
        "session_id": item.session_id,
        "session_name": item.session_name,
        "request_message_key": item.request_message_key,
        "response_message_key": item.response_message_key,
        "request_count": item.request_count,
        "completed_count": item.completed_count,
        "positive_response_count": item.positive_response_count,
        "negative_response_count": item.negative_response_count,
        "timeout_count": item.timeout_count,
        "capture_ended_count": item.capture_ended_count,
        "suppressed_no_response_count": item.suppressed_no_response_count,
        "response_pending_transaction_count": (
            item.response_pending_transaction_count
        ),
        "response_pending_count": item.response_pending_count,
        "unmatched_response_count": item.unmatched_response_count,
        "incomplete_isotp_message_count": item.incomplete_isotp_message_count,
        "completion_rate_percent": item.completion_rate_percent,
        "mean_first_response_latency_ns": item.mean_first_response_latency_ns,
        "p50_first_response_latency_ns": item.p50_first_response_latency_ns,
        "p95_first_response_latency_ns": item.p95_first_response_latency_ns,
        "p99_first_response_latency_ns": item.p99_first_response_latency_ns,
        "mean_final_response_latency_ns": item.mean_final_response_latency_ns,
        "p50_final_response_latency_ns": item.p50_final_response_latency_ns,
        "p95_final_response_latency_ns": item.p95_final_response_latency_ns,
        "p99_final_response_latency_ns": item.p99_final_response_latency_ns,
        "first_latency_sample_count": item.first_latency_sample_count,
        "final_latency_sample_count": item.final_latency_sample_count,
        "transaction_evidence": [
            _transaction_to_payload(value)
            for value in item.transaction_evidence
        ],
        "unmatched_responses": [
            _message_to_payload(value) for value in item.unmatched_responses
        ],
        "evidence_truncated": item.evidence_truncated,
        "warning": item.warning,
    }


def _session_from_payload(value: Any) -> UdsSessionLatencyStatistics:
    payload = _mapping(value, "UDS session latency")
    return UdsSessionLatencyStatistics(
        session_id=str(payload.get("session_id") or ""),
        session_name=str(payload.get("session_name") or ""),
        request_message_key=str(payload.get("request_message_key") or ""),
        response_message_key=str(payload.get("response_message_key") or ""),
        request_count=int(payload.get("request_count", 0)),
        completed_count=int(payload.get("completed_count", 0)),
        positive_response_count=int(
            payload.get("positive_response_count", 0)
        ),
        negative_response_count=int(
            payload.get("negative_response_count", 0)
        ),
        timeout_count=int(payload.get("timeout_count", 0)),
        capture_ended_count=int(payload.get("capture_ended_count", 0)),
        suppressed_no_response_count=int(
            payload.get("suppressed_no_response_count", 0)
        ),
        response_pending_transaction_count=int(
            payload.get("response_pending_transaction_count", 0)
        ),
        response_pending_count=int(payload.get("response_pending_count", 0)),
        unmatched_response_count=int(
            payload.get("unmatched_response_count", 0)
        ),
        incomplete_isotp_message_count=int(
            payload.get("incomplete_isotp_message_count", 0)
        ),
        completion_rate_percent=_optional_float(
            payload.get("completion_rate_percent")
        ),
        mean_first_response_latency_ns=_optional_float(
            payload.get("mean_first_response_latency_ns")
        ),
        p50_first_response_latency_ns=_optional_float(
            payload.get("p50_first_response_latency_ns")
        ),
        p95_first_response_latency_ns=_optional_float(
            payload.get("p95_first_response_latency_ns")
        ),
        p99_first_response_latency_ns=_optional_float(
            payload.get("p99_first_response_latency_ns")
        ),
        mean_final_response_latency_ns=_optional_float(
            payload.get("mean_final_response_latency_ns")
        ),
        p50_final_response_latency_ns=_optional_float(
            payload.get("p50_final_response_latency_ns")
        ),
        p95_final_response_latency_ns=_optional_float(
            payload.get("p95_final_response_latency_ns")
        ),
        p99_final_response_latency_ns=_optional_float(
            payload.get("p99_final_response_latency_ns")
        ),
        first_latency_sample_count=int(
            payload.get("first_latency_sample_count", 0)
        ),
        final_latency_sample_count=int(
            payload.get("final_latency_sample_count", 0)
        ),
        transaction_evidence=tuple(
            _transaction_from_payload(item)
            for item in _sequence(payload.get("transaction_evidence", []))
        ),
        unmatched_responses=tuple(
            _message_from_payload(item)
            for item in _sequence(payload.get("unmatched_responses", []))
        ),
        evidence_truncated=bool(payload.get("evidence_truncated", False)),
        warning=str(payload.get("warning") or ""),
    )


def _transaction_to_payload(item: UdsTransactionEvidence) -> dict[str, Any]:
    return {
        "session_id": item.session_id,
        "session_name": item.session_name,
        "request_service_id": item.request_service_id,
        "request_service_name": item.request_service_name,
        "status": item.status,
        "request": _message_to_payload(item.request),
        "first_response": (
            _message_to_payload(item.first_response)
            if item.first_response is not None
            else None
        ),
        "final_response": (
            _message_to_payload(item.final_response)
            if item.final_response is not None
            else None
        ),
        "pending_responses": [
            _message_to_payload(value) for value in item.pending_responses
        ],
        "response_pending_count": item.response_pending_count,
        "first_response_latency_ns": item.first_response_latency_ns,
        "final_response_latency_ns": item.final_response_latency_ns,
        "final_negative_response_code": item.final_negative_response_code,
        "suppress_positive_response": item.suppress_positive_response,
    }


def _transaction_from_payload(value: Any) -> UdsTransactionEvidence:
    payload = _mapping(value, "UDS transaction evidence")
    first_value = payload.get("first_response")
    final_value = payload.get("final_response")
    return UdsTransactionEvidence(
        session_id=str(payload.get("session_id") or ""),
        session_name=str(payload.get("session_name") or ""),
        request_service_id=int(payload.get("request_service_id", 0)),
        request_service_name=str(payload.get("request_service_name") or ""),
        status=str(payload.get("status") or ""),
        request=_message_from_payload(payload.get("request")),
        first_response=(
            _message_from_payload(first_value)
            if first_value is not None
            else None
        ),
        final_response=(
            _message_from_payload(final_value)
            if final_value is not None
            else None
        ),
        pending_responses=tuple(
            _message_from_payload(item)
            for item in _sequence(payload.get("pending_responses", []))
        ),
        response_pending_count=int(
            payload.get("response_pending_count", 0)
        ),
        first_response_latency_ns=_optional_int(
            payload.get("first_response_latency_ns")
        ),
        final_response_latency_ns=_optional_int(
            payload.get("final_response_latency_ns")
        ),
        final_negative_response_code=_optional_int(
            payload.get("final_negative_response_code")
        ),
        suppress_positive_response=bool(
            payload.get("suppress_positive_response", False)
        ),
    )


def _message_to_payload(item: UdsMessageEvidence) -> dict[str, Any]:
    return {
        "session_id": item.session_id,
        "session_name": item.session_name,
        "message_key": item.message_key,
        "first_source_row": item.first_source_row,
        "last_source_row": item.last_source_row,
        "first_timestamp_ns": item.first_timestamp_ns,
        "last_timestamp_ns": item.last_timestamp_ns,
        "frame_count": item.frame_count,
        "payload_hex": item.payload_hex,
        "service_id": item.service_id,
        "service_name": item.service_name,
        "requested_service_id": item.requested_service_id,
        "negative_response_code": item.negative_response_code,
        "negative_response_name": item.negative_response_name,
        "response_pending": item.response_pending,
        "complete": item.complete,
        "error": item.error,
    }


def _message_from_payload(value: Any) -> UdsMessageEvidence:
    payload = _mapping(value, "UDS message evidence")
    return UdsMessageEvidence(
        session_id=str(payload.get("session_id") or ""),
        session_name=str(payload.get("session_name") or ""),
        message_key=str(payload.get("message_key") or ""),
        first_source_row=int(payload.get("first_source_row", -1)),
        last_source_row=int(payload.get("last_source_row", -1)),
        first_timestamp_ns=int(payload.get("first_timestamp_ns", 0)),
        last_timestamp_ns=int(payload.get("last_timestamp_ns", 0)),
        frame_count=int(payload.get("frame_count", 0)),
        payload_hex=str(payload.get("payload_hex") or ""),
        service_id=_optional_int(payload.get("service_id")),
        service_name=str(payload.get("service_name") or ""),
        requested_service_id=_optional_int(
            payload.get("requested_service_id")
        ),
        negative_response_code=_optional_int(
            payload.get("negative_response_code")
        ),
        negative_response_name=str(
            payload.get("negative_response_name") or ""
        ),
        response_pending=bool(payload.get("response_pending", False)),
        complete=bool(payload.get("complete", False)),
        error=str(payload.get("error") or ""),
    )


def _comparison_to_payload(
    item: UdsSessionLatencyComparison,
) -> dict[str, Any]:
    return {
        "session_id": item.session_id,
        "session_name": item.session_name,
        "baseline_session_id": item.baseline_session_id,
        "completion_rate_delta_percentage_points": (
            item.completion_rate_delta_percentage_points
        ),
        "p50_first_latency_delta_percent": (
            item.p50_first_latency_delta_percent
        ),
        "p50_final_latency_delta_percent": (
            item.p50_final_latency_delta_percent
        ),
        "p95_final_latency_delta_percent": (
            item.p95_final_latency_delta_percent
        ),
        "timeout_count_delta": item.timeout_count_delta,
        "negative_response_count_delta": (
            item.negative_response_count_delta
        ),
        "response_pending_count_delta": (
            item.response_pending_count_delta
        ),
        "unmatched_response_count_delta": (
            item.unmatched_response_count_delta
        ),
    }


def _comparison_from_payload(value: Any) -> UdsSessionLatencyComparison:
    payload = _mapping(value, "UDS session comparison")
    return UdsSessionLatencyComparison(
        session_id=str(payload.get("session_id") or ""),
        session_name=str(payload.get("session_name") or ""),
        baseline_session_id=str(payload.get("baseline_session_id") or ""),
        completion_rate_delta_percentage_points=_optional_float(
            payload.get("completion_rate_delta_percentage_points")
        ),
        p50_first_latency_delta_percent=_optional_float(
            payload.get("p50_first_latency_delta_percent")
        ),
        p50_final_latency_delta_percent=_optional_float(
            payload.get("p50_final_latency_delta_percent")
        ),
        p95_final_latency_delta_percent=_optional_float(
            payload.get("p95_final_latency_delta_percent")
        ),
        timeout_count_delta=int(payload.get("timeout_count_delta", 0)),
        negative_response_count_delta=int(
            payload.get("negative_response_count_delta", 0)
        ),
        response_pending_count_delta=int(
            payload.get("response_pending_count_delta", 0)
        ),
        unmatched_response_count_delta=int(
            payload.get("unmatched_response_count_delta", 0)
        ),
    )


def _validate_fingerprints(
    payload: Mapping[str, Any],
    records: tuple[SessionRecord, ...],
) -> None:
    values = _sequence(payload.get("session_fingerprints"))
    if len(values) != len(records):
        raise StaleUdsLatencyArtifact("session fingerprint count changed")
    for record, value in zip(records, values, strict=True):
        fingerprint = _mapping(value, "session fingerprint")
        if str(fingerprint.get("session_id") or "") != record.id:
            raise StaleUdsLatencyArtifact("session order changed")
        if int(fingerprint.get("frame_count", -1)) != record.frame_count:
            raise StaleUdsLatencyArtifact(
                f"session frame count changed: {record.name}"
            )
        saved_sha = str(fingerprint.get("sha256") or "")
        if saved_sha and record.sha256 and saved_sha != record.sha256:
            raise StaleUdsLatencyArtifact(
                f"session SHA-256 changed: {record.name}"
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
    return (
        not frame.is_remote_frame
        and not frame.is_error_frame
        and key.frame_kind == "data"
    )


def _optional_normalized_key(value: str) -> str:
    return (
        format_timeline_message_key(parse_timeline_message_key(value))
        if str(value).strip()
        else ""
    )


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
    replacement = _splitmix64(seed ^ count) % count
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
        raise UdsLatencyCancelled


__all__ = [
    "ComparisonUdsLatencyService",
    "DEFAULT_MAXIMUM_TRANSACTION_EVIDENCE",
    "DEFAULT_PERCENTILE_SAMPLE_LIMIT",
    "DEFAULT_TIMEOUT_MS",
    "StaleUdsLatencyArtifact",
    "StoredUdsLatency",
    "UDS_LATENCY_ARTIFACT_TYPE",
    "UDS_LATENCY_SCHEMA",
    "UdsLatencyCancelled",
    "UdsLatencyConfiguration",
    "UdsLatencyExecutionResult",
    "UdsLatencyResult",
    "UdsMessageEvidence",
    "UdsSessionLatencyComparison",
    "UdsSessionLatencyStatistics",
    "UdsTransactionEvidence",
    "analyze_comparison_uds_latency",
    "normalize_uds_latency_configuration",
    "uds_latency_result_from_payload",
    "uds_latency_result_to_payload",
]
