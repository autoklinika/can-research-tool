from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from .comparison_timeline_artifacts import (
    ComparisonTimelineArtifactService,
    StoredComparisonTimeline,
)
from .comparison_uds_explorer_source import (
    PreferredUdsLatencySource,
    load_preferred_uds_latency_source,
)
from .comparison_uds_latency import (
    ComparisonUdsLatencyService,
    UdsTransactionEvidence,
)
from .comparison_uds_transaction_explorer import (
    UdsTransactionRecord,
    build_uds_transaction_explorer,
)
from .domain import ComparisonSet
from .project import CrtProject


@dataclass(frozen=True, slots=True)
class UdsTimelineFilter:
    session_ids: tuple[str, ...] = ()
    service_ids: tuple[int, ...] = ()
    statuses: tuple[str, ...] = ()
    dids: tuple[int, ...] = ()
    negative_response_codes: tuple[int, ...] = ()
    text_query: str = ""


@dataclass(frozen=True, slots=True)
class UdsTimelineSources:
    alignment: StoredComparisonTimeline
    uds: PreferredUdsLatencySource


@dataclass(frozen=True, slots=True)
class UdsTimelineTransaction:
    record: UdsTransactionRecord
    request_relative_time_ns: int
    first_response_relative_time_ns: int | None
    final_response_relative_time_ns: int | None
    pending_relative_times_ns: tuple[int, ...]
    sequence_classification: str

    @property
    def transaction(self) -> UdsTransactionEvidence:
        return self.record.transaction


@dataclass(frozen=True, slots=True)
class UdsTimelineLane:
    session_id: str
    session_name: str
    is_baseline: bool
    anchor_source_row: int
    anchor_timestamp_ns: int
    transactions: tuple[UdsTimelineTransaction, ...]
    evidence_truncated: bool
    warning: str = ""


@dataclass(frozen=True, slots=True)
class UdsTimelineSequenceDifference:
    session_id: str
    session_name: str
    baseline_session_id: str
    missing_count: int
    additional_count: int
    shifted_count: int
    missing_labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UdsTimelineResult:
    alignment_artifact_id: str
    uds_artifact_id: str
    skipped_newer_empty_uds_artifacts: int
    baseline_session_id: str
    lanes: tuple[UdsTimelineLane, ...]
    differences: tuple[UdsTimelineSequenceDifference, ...]
    minimum_relative_time_ns: int
    maximum_relative_time_ns: int
    source_transaction_count: int
    visible_transaction_count: int
    warnings: tuple[str, ...]


class UdsTimelineCancelled(RuntimeError):
    """Raised when artifact-backed UDS timeline loading is cancelled."""


def load_uds_timeline_sources(
    project: CrtProject,
    comparison_set: ComparisonSet,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> UdsTimelineSources:
    """Load compatible Stage 2B and Stage 2C2 artifacts without session scans."""

    alignment = ComparisonTimelineArtifactService(project).load_latest_compatible(
        comparison_set,
        should_cancel=should_cancel,
    )
    _raise_if_cancelled(should_cancel)
    if alignment is None:
        raise ValueError(
            "Brak zgodnego zapisanego wyrównania Stage 2B. "
            "Otwórz kartę Oś czasu, zbuduj wyrównanie i zapisz artefakt."
        )

    uds = load_preferred_uds_latency_source(
        ComparisonUdsLatencyService(project),
        comparison_set,
        should_cancel=should_cancel,
    )
    _raise_if_cancelled(should_cancel)
    if uds.stored is None:
        raise ValueError(
            "Brak zgodnego artefaktu Stage 2C2. Otwórz kartę Latencja UDS "
            "i przeprowadź analizę dla właściwych kluczy request/response."
        )
    return UdsTimelineSources(alignment=alignment, uds=uds)


def build_uds_timeline(
    sources: UdsTimelineSources,
    *,
    filter_specification: UdsTimelineFilter | None = None,
) -> UdsTimelineResult:
    """Project saved UDS evidence onto a saved synchronized timeline."""

    filter_specification = _normalize_filter(
        filter_specification or UdsTimelineFilter()
    )
    stored_uds = sources.uds.stored
    if stored_uds is None:
        raise ValueError("Brak źródłowego artefaktu UDS.")

    alignment = sources.alignment.result
    uds_result = stored_uds.result
    explorer = build_uds_transaction_explorer(
        uds_result,
        source_artifact_id=stored_uds.artifact.id,
    )
    records_by_session: dict[str, list[UdsTransactionRecord]] = defaultdict(list)
    for record in explorer.visible_transactions:
        if _matches_non_session_filter(record, filter_specification):
            records_by_session[record.transaction.session_id].append(record)
    for records in records_by_session.values():
        records.sort(
            key=lambda item: (
                item.transaction.request.first_timestamp_ns,
                item.transaction.request.first_source_row,
            )
        )

    baseline_records = records_by_session.get(uds_result.baseline_session_id, [])
    classifications: dict[str, tuple[str, ...]] = {
        uds_result.baseline_session_id: tuple("baseline" for _ in baseline_records)
    }
    differences: list[UdsTimelineSequenceDifference] = []
    for session in uds_result.sessions:
        if session.session_id == uds_result.baseline_session_id:
            continue
        current = records_by_session.get(session.session_id, [])
        labels, missing_labels = _compare_sequences(baseline_records, current)
        classifications[session.session_id] = labels
        differences.append(
            UdsTimelineSequenceDifference(
                session_id=session.session_id,
                session_name=session.session_name,
                baseline_session_id=uds_result.baseline_session_id,
                missing_count=len(missing_labels),
                additional_count=sum(1 for value in labels if value == "additional"),
                shifted_count=sum(1 for value in labels if value == "shifted"),
                missing_labels=missing_labels,
            )
        )

    stats_by_session = {item.session_id: item for item in uds_result.sessions}
    selected_sessions = set(filter_specification.session_ids)
    lanes: list[UdsTimelineLane] = []
    visible_count = 0
    warnings: list[str] = list(explorer.warnings)

    for alignment_lane in alignment.lanes:
        if selected_sessions and alignment_lane.session_id not in selected_sessions:
            continue
        if not alignment_lane.synchronized or alignment_lane.anchor_timestamp_ns is None:
            warnings.append(
                f"Sesja {alignment_lane.session_name} nie ma zgodnej kotwicy Stage 2B."
            )
            continue
        records = records_by_session.get(alignment_lane.session_id, [])
        labels = classifications.get(
            alignment_lane.session_id,
            tuple("matched" for _ in records),
        )
        projected = tuple(
            _project_transaction(record, alignment_lane.anchor_timestamp_ns, label)
            for record, label in zip(records, labels, strict=False)
        )
        visible_count += len(projected)
        stats = stats_by_session.get(alignment_lane.session_id)
        lanes.append(
            UdsTimelineLane(
                session_id=alignment_lane.session_id,
                session_name=alignment_lane.session_name,
                is_baseline=alignment_lane.session_id == uds_result.baseline_session_id,
                anchor_source_row=int(alignment_lane.anchor_source_row or 0),
                anchor_timestamp_ns=int(alignment_lane.anchor_timestamp_ns),
                transactions=projected,
                evidence_truncated=bool(stats and stats.evidence_truncated),
                warning=alignment_lane.warning,
            )
        )

    if not lanes:
        warnings.append("Aktywne filtry lub brak kotwic ukrywają wszystkie pasy UDS.")
    elif visible_count == 0:
        warnings.append("Aktywne filtry nie pozostawiły żadnych transakcji UDS.")

    return UdsTimelineResult(
        alignment_artifact_id=sources.alignment.artifact.id,
        uds_artifact_id=stored_uds.artifact.id,
        skipped_newer_empty_uds_artifacts=(
            sources.uds.skipped_newer_empty_artifacts
        ),
        baseline_session_id=uds_result.baseline_session_id,
        lanes=tuple(lanes),
        differences=tuple(differences),
        minimum_relative_time_ns=alignment.minimum_relative_time_ns,
        maximum_relative_time_ns=alignment.maximum_relative_time_ns,
        source_transaction_count=explorer.source_transaction_count,
        visible_transaction_count=visible_count,
        warnings=tuple(dict.fromkeys(value for value in warnings if value)),
    )


def _project_transaction(
    record: UdsTransactionRecord,
    anchor_timestamp_ns: int,
    classification: str,
) -> UdsTimelineTransaction:
    transaction = record.transaction
    return UdsTimelineTransaction(
        record=record,
        request_relative_time_ns=(
            transaction.request.first_timestamp_ns - anchor_timestamp_ns
        ),
        first_response_relative_time_ns=(
            None
            if transaction.first_response is None
            else transaction.first_response.first_timestamp_ns - anchor_timestamp_ns
        ),
        final_response_relative_time_ns=(
            None
            if transaction.final_response is None
            else transaction.final_response.last_timestamp_ns - anchor_timestamp_ns
        ),
        pending_relative_times_ns=tuple(
            item.first_timestamp_ns - anchor_timestamp_ns
            for item in transaction.pending_responses
        ),
        sequence_classification=classification,
    )


def _compare_sequences(
    baseline: Sequence[UdsTransactionRecord],
    current: Sequence[UdsTransactionRecord],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Classify preserved order, movement and additions with duplicate-safe pairing."""

    base_keys = [item.automatic_correlation_key for item in baseline]
    current_keys = [item.automatic_correlation_key for item in current]
    labels = ["additional"] * len(current)
    matched_base: set[int] = set()
    matched_current: set[int] = set()

    matcher = SequenceMatcher(a=base_keys, b=current_keys, autojunk=False)
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            base_index = block.a + offset
            current_index = block.b + offset
            matched_base.add(base_index)
            matched_current.add(current_index)
            labels[current_index] = "matched"

    remaining_by_key: dict[str, deque[int]] = defaultdict(deque)
    for base_index, key in enumerate(base_keys):
        if base_index not in matched_base:
            remaining_by_key[key].append(base_index)

    for current_index, key in enumerate(current_keys):
        if current_index in matched_current:
            continue
        queue = remaining_by_key.get(key)
        if queue:
            base_index = queue.popleft()
            matched_base.add(base_index)
            labels[current_index] = "shifted"

    missing = tuple(
        baseline[index].automatic_correlation_label
        for index in range(len(baseline))
        if index not in matched_base
    )
    return tuple(labels), missing


def _matches_non_session_filter(
    record: UdsTransactionRecord,
    specification: UdsTimelineFilter,
) -> bool:
    transaction = record.transaction
    if specification.service_ids and (
        transaction.request_service_id not in specification.service_ids
    ):
        return False
    if specification.statuses and transaction.status not in specification.statuses:
        return False
    if specification.dids and record.did not in specification.dids:
        return False
    if specification.negative_response_codes and (
        transaction.final_negative_response_code
        not in specification.negative_response_codes
    ):
        return False
    query = specification.text_query.casefold().strip()
    if query:
        haystack = " ".join(
            (
                transaction.request_service_name,
                transaction.status,
                record.automatic_correlation_label,
                transaction.request.payload_hex,
                "" if transaction.first_response is None else transaction.first_response.payload_hex,
                "" if transaction.final_response is None else transaction.final_response.payload_hex,
            )
        ).casefold()
        if query not in haystack:
            return False
    return True


def _normalize_filter(specification: UdsTimelineFilter) -> UdsTimelineFilter:
    return UdsTimelineFilter(
        session_ids=tuple(dict.fromkeys(str(value) for value in specification.session_ids)),
        service_ids=tuple(dict.fromkeys(int(value) for value in specification.service_ids)),
        statuses=tuple(dict.fromkeys(str(value) for value in specification.statuses)),
        dids=tuple(dict.fromkeys(int(value) for value in specification.dids)),
        negative_response_codes=tuple(
            dict.fromkeys(int(value) for value in specification.negative_response_codes)
        ),
        text_query=str(specification.text_query).strip(),
    )


def _raise_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise UdsTimelineCancelled("UDS timeline loading cancelled")


__all__ = [
    "UdsTimelineCancelled",
    "UdsTimelineFilter",
    "UdsTimelineLane",
    "UdsTimelineResult",
    "UdsTimelineSequenceDifference",
    "UdsTimelineSources",
    "UdsTimelineTransaction",
    "build_uds_timeline",
    "load_uds_timeline_sources",
]
