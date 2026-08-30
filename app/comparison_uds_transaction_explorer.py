from __future__ import annotations

import csv
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .comparison_uds_latency import UdsLatencyResult, UdsTransactionEvidence
from .protocol_catalog import UDS_SUBFUNCTION_SERVICES, uds_nrc_name

GROUPING_MODES = ("auto", "service", "did", "subfunction", "routine")
COMPLETED_STATUSES = frozenset({"positive-response", "negative-response"})


@dataclass(frozen=True, slots=True)
class UdsExplorerFilter:
    session_ids: tuple[str, ...] = ()
    service_ids: tuple[int, ...] = ()
    statuses: tuple[str, ...] = ()
    negative_response_codes: tuple[int, ...] = ()
    text_query: str = ""
    start_time_ms: float | None = None
    end_time_ms: float | None = None
    minimum_final_latency_ms: float | None = None
    maximum_final_latency_ms: float | None = None


@dataclass(frozen=True, slots=True)
class UdsTransactionRecord:
    transaction: UdsTransactionEvidence
    relative_request_time_ms: float
    request_payload: bytes
    first_response_payload: bytes
    final_response_payload: bytes
    did: int | None
    subfunction: int | None
    routine_id: int | None
    automatic_correlation_key: str
    automatic_correlation_label: str


@dataclass(frozen=True, slots=True)
class UdsTransactionGroup:
    grouping_mode: str
    group_key: str
    group_label: str
    session_id: str
    session_name: str
    transaction_count: int
    positive_response_count: int
    negative_response_count: int
    timeout_count: int
    capture_ended_count: int
    suppressed_no_response_count: int
    response_pending_transaction_count: int
    response_pending_count: int
    completion_rate_percent: float | None
    p50_first_response_latency_ns: float | None
    p95_first_response_latency_ns: float | None
    p50_final_response_latency_ns: float | None
    p95_final_response_latency_ns: float | None


@dataclass(frozen=True, slots=True)
class UdsTransactionGroupComparison:
    grouping_mode: str
    group_key: str
    group_label: str
    session_id: str
    session_name: str
    baseline_session_id: str
    transaction_count_delta: int
    completion_rate_delta_percentage_points: float | None
    p50_first_latency_delta_percent: float | None
    p50_final_latency_delta_percent: float | None
    p95_final_latency_delta_percent: float | None
    timeout_count_delta: int
    negative_response_count_delta: int
    response_pending_count_delta: int


@dataclass(frozen=True, slots=True)
class UdsLatencyDistribution:
    session_id: str
    session_name: str
    transaction_count: int
    p50_first_response_latency_ns: float | None
    p95_first_response_latency_ns: float | None
    p50_final_response_latency_ns: float | None
    p95_final_response_latency_ns: float | None


@dataclass(frozen=True, slots=True)
class UdsTransactionExplorerResult:
    source_artifact_id: str
    grouping_mode: str
    filter_specification: UdsExplorerFilter
    source_transaction_count: int
    visible_transactions: tuple[UdsTransactionRecord, ...]
    groups: tuple[UdsTransactionGroup, ...]
    comparisons: tuple[UdsTransactionGroupComparison, ...]
    distributions: tuple[UdsLatencyDistribution, ...]
    warnings: tuple[str, ...]


def build_uds_transaction_explorer(
    latency_result: UdsLatencyResult,
    *,
    source_artifact_id: str = "",
    filter_specification: UdsExplorerFilter | None = None,
    grouping_mode: str = "auto",
) -> UdsTransactionExplorerResult:
    filter_specification = _normalize_filter(
        filter_specification or UdsExplorerFilter()
    )
    grouping_mode = str(grouping_mode or "auto").strip().lower()
    if grouping_mode not in GROUPING_MODES:
        raise ValueError(
            f"unsupported UDS transaction grouping mode: {grouping_mode}"
        )

    origins = {
        session.session_id: min(
            (
                item.request.first_timestamp_ns
                for item in session.transaction_evidence
            ),
            default=0,
        )
        for session in latency_result.sessions
    }
    records = tuple(
        _record_from_transaction(
            item,
            origins.get(session.session_id, 0),
        )
        for session in latency_result.sessions
        for item in session.transaction_evidence
    )
    visible = tuple(
        sorted(
            (
                item
                for item in records
                if _matches_filter(item, filter_specification)
            ),
            key=lambda item: (
                _session_order(
                    latency_result,
                    item.transaction.session_id,
                ),
                item.transaction.request.first_timestamp_ns,
                item.transaction.request.first_source_row,
            ),
        )
    )
    groups = _build_groups(
        latency_result,
        visible,
        grouping_mode,
    )
    comparisons = _build_group_comparisons(
        latency_result,
        groups,
        grouping_mode,
    )
    distributions = _build_distributions(latency_result, visible)

    warnings: list[str] = []
    truncated_sessions = [
        session.session_name
        for session in latency_result.sessions
        if session.evidence_truncated
    ]
    if truncated_sessions:
        warnings.append(
            "Grupowanie i eksport działają na bounded parach dowodowych "
            "Stage 2C2. Dokładne liczniki globalne pozostają w karcie "
            "Latencja UDS. Ograniczone sesje: "
            + ", ".join(truncated_sessions)
            + "."
        )
    if records and not visible:
        warnings.append(
            "Aktywne filtry ukrywają wszystkie zachowane transakcje."
        )
    if not records:
        warnings.append(
            "Artefakt Stage 2C2 nie zawiera zachowanych transakcji "
            "dowodowych."
        )

    return UdsTransactionExplorerResult(
        source_artifact_id=str(source_artifact_id),
        grouping_mode=grouping_mode,
        filter_specification=filter_specification,
        source_transaction_count=len(records),
        visible_transactions=visible,
        groups=groups,
        comparisons=comparisons,
        distributions=distributions,
        warnings=tuple(warnings),
    )


def export_transactions_csv(
    path: str | Path,
    records: Sequence[UdsTransactionRecord],
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(
            [
                "session_id",
                "session_name",
                "relative_request_time_ms",
                "request_source_row",
                "service_id",
                "service_name",
                "status",
                "did",
                "subfunction",
                "routine_id",
                "response_pending_count",
                "first_response_latency_ms",
                "final_response_latency_ms",
                "final_nrc",
                "request_payload",
                "first_response_payload",
                "final_response_payload",
                "request_message_key",
                "first_response_source_row",
                "final_response_source_row",
            ]
        )
        for record in records:
            transaction = record.transaction
            writer.writerow(
                [
                    transaction.session_id,
                    transaction.session_name,
                    f"{record.relative_request_time_ms:.6f}",
                    transaction.request.first_source_row,
                    f"0x{transaction.request_service_id:02X}",
                    transaction.request_service_name,
                    transaction.status,
                    _hex_optional(record.did, 4),
                    _hex_optional(record.subfunction, 2),
                    _hex_optional(record.routine_id, 4),
                    transaction.response_pending_count,
                    _ms_number(
                        transaction.first_response_latency_ns
                    ),
                    _ms_number(
                        transaction.final_response_latency_ns
                    ),
                    _hex_optional(
                        transaction.final_negative_response_code,
                        2,
                    ),
                    transaction.request.payload_hex,
                    (
                        ""
                        if transaction.first_response is None
                        else transaction.first_response.payload_hex
                    ),
                    (
                        ""
                        if transaction.final_response is None
                        else transaction.final_response.payload_hex
                    ),
                    transaction.request.message_key,
                    (
                        ""
                        if transaction.first_response is None
                        else transaction.first_response.first_source_row
                    ),
                    (
                        ""
                        if transaction.final_response is None
                        else transaction.final_response.first_source_row
                    ),
                ]
            )
    return destination


def export_groups_csv(
    path: str | Path,
    groups: Sequence[UdsTransactionGroup],
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(
            [
                "grouping_mode",
                "group_key",
                "group_label",
                "session_id",
                "session_name",
                "transaction_count",
                "positive_response_count",
                "negative_response_count",
                "timeout_count",
                "capture_ended_count",
                "suppressed_no_response_count",
                "response_pending_transaction_count",
                "response_pending_count",
                "completion_rate_percent",
                "p50_first_response_latency_ms",
                "p95_first_response_latency_ms",
                "p50_final_response_latency_ms",
                "p95_final_response_latency_ms",
            ]
        )
        for item in groups:
            writer.writerow(
                [
                    item.grouping_mode,
                    item.group_key,
                    item.group_label,
                    item.session_id,
                    item.session_name,
                    item.transaction_count,
                    item.positive_response_count,
                    item.negative_response_count,
                    item.timeout_count,
                    item.capture_ended_count,
                    item.suppressed_no_response_count,
                    item.response_pending_transaction_count,
                    item.response_pending_count,
                    _number(item.completion_rate_percent),
                    _ms_number(
                        item.p50_first_response_latency_ns
                    ),
                    _ms_number(
                        item.p95_first_response_latency_ns
                    ),
                    _ms_number(
                        item.p50_final_response_latency_ns
                    ),
                    _ms_number(
                        item.p95_final_response_latency_ns
                    ),
                ]
            )
    return destination


def format_transaction_details(
    record: UdsTransactionRecord,
) -> str:
    transaction = record.transaction
    first = transaction.first_response
    final = transaction.final_response
    lines = [
        (
            f"Sesja: {transaction.session_name} "
            f"({transaction.session_id})"
        ),
        (
            f"Czas względny żądania: "
            f"{record.relative_request_time_ms:.3f} ms; "
            f"source_row={transaction.request.first_source_row}"
        ),
        (
            f"Usługa: 0x{transaction.request_service_id:02X} "
            f"{transaction.request_service_name}"
        ),
        f"Korelacja: {record.automatic_correlation_label}",
        f"Status: {transaction.status}",
        f"ResponsePending: {transaction.response_pending_count}",
        (
            "First response latency: "
            + _ms_text(transaction.first_response_latency_ns)
        ),
        (
            "Final response latency: "
            + _ms_text(transaction.final_response_latency_ns)
        ),
        (
            "Final NRC: —"
            if transaction.final_negative_response_code is None
            else (
                "Final NRC: "
                f"0x{transaction.final_negative_response_code:02X} "
                f"{uds_nrc_name(transaction.final_negative_response_code)}"
            )
        ),
        "",
        "Żądanie:",
        _message_details(transaction.request),
        "",
        "Pierwsza odpowiedź:",
        "—" if first is None else _message_details(first),
        "",
        "Odpowiedź końcowa:",
        "—" if final is None else _message_details(final),
    ]
    if transaction.pending_responses:
        lines.extend(["", "Odpowiedzi 0x78:"])
        for index, pending in enumerate(
            transaction.pending_responses,
            start=1,
        ):
            lines.append(
                f"{index}. row={pending.first_source_row}, "
                f"t={pending.first_timestamp_ns}, "
                f"payload={pending.payload_hex}"
            )
    return "\n".join(lines)


def _record_from_transaction(
    transaction: UdsTransactionEvidence,
    origin_timestamp_ns: int,
) -> UdsTransactionRecord:
    request_payload = _payload_bytes(
        transaction.request.payload_hex
    )
    first_payload = (
        b""
        if transaction.first_response is None
        else _payload_bytes(
            transaction.first_response.payload_hex
        )
    )
    final_payload = (
        b""
        if transaction.final_response is None
        else _payload_bytes(
            transaction.final_response.payload_hex
        )
    )
    sid = transaction.request_service_id
    subfunction = (
        request_payload[1] & 0x7F
        if sid in UDS_SUBFUNCTION_SERVICES
        and len(request_payload) >= 2
        else None
    )
    did = (
        int.from_bytes(request_payload[1:3], "big")
        if sid in {0x22, 0x24, 0x2A, 0x2E, 0x2F}
        and len(request_payload) >= 3
        else None
    )
    routine_id = (
        int.from_bytes(request_payload[2:4], "big")
        if sid == 0x31 and len(request_payload) >= 4
        else None
    )
    key, label = _automatic_correlation(
        sid,
        transaction.request_service_name,
        did=did,
        subfunction=subfunction,
        routine_id=routine_id,
    )
    relative_ms = (
        max(
            0,
            transaction.request.first_timestamp_ns
            - origin_timestamp_ns,
        )
        / 1_000_000.0
    )
    return UdsTransactionRecord(
        transaction=transaction,
        relative_request_time_ms=relative_ms,
        request_payload=request_payload,
        first_response_payload=first_payload,
        final_response_payload=final_payload,
        did=did,
        subfunction=subfunction,
        routine_id=routine_id,
        automatic_correlation_key=key,
        automatic_correlation_label=label,
    )


def _automatic_correlation(
    sid: int,
    service_name: str,
    *,
    did: int | None,
    subfunction: int | None,
    routine_id: int | None,
) -> tuple[str, str]:
    if routine_id is not None:
        sub = (
            "—"
            if subfunction is None
            else f"0x{subfunction:02X}"
        )
        return (
            f"sid:{sid:02X}:routine:{routine_id:04X}:"
            f"sub:{subfunction if subfunction is not None else -1}",
            (
                f"0x{sid:02X} {service_name} / "
                f"Routine 0x{routine_id:04X} / sub {sub}"
            ),
        )
    if did is not None:
        return (
            f"sid:{sid:02X}:did:{did:04X}",
            (
                f"0x{sid:02X} {service_name} / "
                f"DID 0x{did:04X}"
            ),
        )
    if subfunction is not None:
        return (
            f"sid:{sid:02X}:sub:{subfunction:02X}",
            (
                f"0x{sid:02X} {service_name} / "
                f"sub 0x{subfunction:02X}"
            ),
        )
    return (
        f"sid:{sid:02X}",
        f"0x{sid:02X} {service_name}",
    )


def _group_identity(
    record: UdsTransactionRecord,
    grouping_mode: str,
) -> tuple[str, str]:
    transaction = record.transaction
    sid = transaction.request_service_id
    service = transaction.request_service_name
    if grouping_mode == "auto":
        return (
            record.automatic_correlation_key,
            record.automatic_correlation_label,
        )
    if grouping_mode == "service":
        return (
            f"sid:{sid:02X}",
            f"0x{sid:02X} {service}",
        )
    if grouping_mode == "did":
        suffix = (
            "none"
            if record.did is None
            else f"{record.did:04X}"
        )
        label = (
            f"0x{sid:02X} {service} / bez DID"
            if record.did is None
            else (
                f"0x{sid:02X} {service} / "
                f"DID 0x{record.did:04X}"
            )
        )
        return f"sid:{sid:02X}:did:{suffix}", label
    if grouping_mode == "subfunction":
        suffix = (
            "none"
            if record.subfunction is None
            else f"{record.subfunction:02X}"
        )
        label = (
            f"0x{sid:02X} {service} / bez subfunkcji"
            if record.subfunction is None
            else (
                f"0x{sid:02X} {service} / "
                f"sub 0x{record.subfunction:02X}"
            )
        )
        return f"sid:{sid:02X}:sub:{suffix}", label
    suffix = (
        "none"
        if record.routine_id is None
        else f"{record.routine_id:04X}"
    )
    label = (
        f"0x{sid:02X} {service} / bez Routine ID"
        if record.routine_id is None
        else (
            f"0x{sid:02X} {service} / "
            f"Routine 0x{record.routine_id:04X}"
        )
    )
    return f"sid:{sid:02X}:routine:{suffix}", label


def _build_groups(
    latency_result: UdsLatencyResult,
    records: Sequence[UdsTransactionRecord],
    grouping_mode: str,
) -> tuple[UdsTransactionGroup, ...]:
    labels: dict[str, str] = {}
    buckets: dict[
        tuple[str, str],
        list[UdsTransactionRecord],
    ] = defaultdict(list)
    for record in records:
        key, label = _group_identity(record, grouping_mode)
        labels.setdefault(key, label)
        buckets[
            (record.transaction.session_id, key)
        ].append(record)

    keys = sorted(
        labels,
        key=lambda value: labels[value].casefold(),
    )
    result: list[UdsTransactionGroup] = []
    for session in latency_result.sessions:
        for key in keys:
            values = buckets.get(
                (session.session_id, key),
                [],
            )
            result.append(
                _summarize_group(
                    grouping_mode,
                    key,
                    labels[key],
                    session.session_id,
                    session.session_name,
                    values,
                )
            )
    return tuple(result)


def _summarize_group(
    grouping_mode: str,
    key: str,
    label: str,
    session_id: str,
    session_name: str,
    values: Sequence[UdsTransactionRecord],
) -> UdsTransactionGroup:
    statuses = [
        item.transaction.status
        for item in values
    ]
    first_latencies = sorted(
        int(item.transaction.first_response_latency_ns)
        for item in values
        if item.transaction.first_response_latency_ns
        is not None
    )
    final_latencies = sorted(
        int(item.transaction.final_response_latency_ns)
        for item in values
        if item.transaction.final_response_latency_ns
        is not None
    )
    completed = sum(
        status in COMPLETED_STATUSES
        for status in statuses
    )
    count = len(values)
    return UdsTransactionGroup(
        grouping_mode=grouping_mode,
        group_key=key,
        group_label=label,
        session_id=session_id,
        session_name=session_name,
        transaction_count=count,
        positive_response_count=statuses.count(
            "positive-response"
        ),
        negative_response_count=statuses.count(
            "negative-response"
        ),
        timeout_count=statuses.count("timeout"),
        capture_ended_count=statuses.count(
            "capture-ended"
        ),
        suppressed_no_response_count=statuses.count(
            "suppressed-no-response"
        ),
        response_pending_transaction_count=sum(
            item.transaction.response_pending_count > 0
            for item in values
        ),
        response_pending_count=sum(
            item.transaction.response_pending_count
            for item in values
        ),
        completion_rate_percent=(
            completed / count * 100.0
            if count
            else None
        ),
        p50_first_response_latency_ns=_percentile(
            first_latencies,
            50,
        ),
        p95_first_response_latency_ns=_percentile(
            first_latencies,
            95,
        ),
        p50_final_response_latency_ns=_percentile(
            final_latencies,
            50,
        ),
        p95_final_response_latency_ns=_percentile(
            final_latencies,
            95,
        ),
    )


def _build_group_comparisons(
    latency_result: UdsLatencyResult,
    groups: Sequence[UdsTransactionGroup],
    grouping_mode: str,
) -> tuple[UdsTransactionGroupComparison, ...]:
    baseline_id = latency_result.baseline_session_id
    by_key = {
        (item.session_id, item.group_key): item
        for item in groups
    }
    keys = tuple(
        dict.fromkeys(
            item.group_key
            for item in groups
        )
    )
    result: list[UdsTransactionGroupComparison] = []
    for session in latency_result.sessions:
        if session.session_id == baseline_id:
            continue
        for key in keys:
            baseline = by_key.get((baseline_id, key))
            current = by_key.get(
                (session.session_id, key)
            )
            if baseline is None or current is None:
                continue
            result.append(
                UdsTransactionGroupComparison(
                    grouping_mode=grouping_mode,
                    group_key=key,
                    group_label=current.group_label,
                    session_id=session.session_id,
                    session_name=session.session_name,
                    baseline_session_id=baseline_id,
                    transaction_count_delta=(
                        current.transaction_count
                        - baseline.transaction_count
                    ),
                    completion_rate_delta_percentage_points=(
                        _difference(
                            current.completion_rate_percent,
                            baseline.completion_rate_percent,
                        )
                    ),
                    p50_first_latency_delta_percent=(
                        _percent_change(
                            current.p50_first_response_latency_ns,
                            baseline.p50_first_response_latency_ns,
                        )
                    ),
                    p50_final_latency_delta_percent=(
                        _percent_change(
                            current.p50_final_response_latency_ns,
                            baseline.p50_final_response_latency_ns,
                        )
                    ),
                    p95_final_latency_delta_percent=(
                        _percent_change(
                            current.p95_final_response_latency_ns,
                            baseline.p95_final_response_latency_ns,
                        )
                    ),
                    timeout_count_delta=(
                        current.timeout_count
                        - baseline.timeout_count
                    ),
                    negative_response_count_delta=(
                        current.negative_response_count
                        - baseline.negative_response_count
                    ),
                    response_pending_count_delta=(
                        current.response_pending_count
                        - baseline.response_pending_count
                    ),
                )
            )
    return tuple(result)


def _build_distributions(
    latency_result: UdsLatencyResult,
    records: Sequence[UdsTransactionRecord],
) -> tuple[UdsLatencyDistribution, ...]:
    by_session: dict[
        str,
        list[UdsTransactionRecord],
    ] = defaultdict(list)
    for record in records:
        by_session[
            record.transaction.session_id
        ].append(record)

    result: list[UdsLatencyDistribution] = []
    for session in latency_result.sessions:
        values = by_session.get(
            session.session_id,
            [],
        )
        first = sorted(
            int(
                item.transaction.first_response_latency_ns
            )
            for item in values
            if item.transaction.first_response_latency_ns
            is not None
        )
        final = sorted(
            int(
                item.transaction.final_response_latency_ns
            )
            for item in values
            if item.transaction.final_response_latency_ns
            is not None
        )
        result.append(
            UdsLatencyDistribution(
                session_id=session.session_id,
                session_name=session.session_name,
                transaction_count=len(values),
                p50_first_response_latency_ns=(
                    _percentile(first, 50)
                ),
                p95_first_response_latency_ns=(
                    _percentile(first, 95)
                ),
                p50_final_response_latency_ns=(
                    _percentile(final, 50)
                ),
                p95_final_response_latency_ns=(
                    _percentile(final, 95)
                ),
            )
        )
    return tuple(result)


def _matches_filter(
    record: UdsTransactionRecord,
    specification: UdsExplorerFilter,
) -> bool:
    transaction = record.transaction
    if (
        specification.session_ids
        and transaction.session_id
        not in specification.session_ids
    ):
        return False
    if (
        specification.service_ids
        and transaction.request_service_id
        not in specification.service_ids
    ):
        return False
    if (
        specification.statuses
        and transaction.status
        not in specification.statuses
    ):
        return False
    if specification.negative_response_codes:
        if (
            transaction.final_negative_response_code
            not in specification.negative_response_codes
        ):
            return False
    if (
        specification.start_time_ms is not None
        and record.relative_request_time_ms
        < specification.start_time_ms
    ):
        return False
    if (
        specification.end_time_ms is not None
        and record.relative_request_time_ms
        > specification.end_time_ms
    ):
        return False

    final_latency_ms = (
        None
        if transaction.final_response_latency_ns is None
        else (
            transaction.final_response_latency_ns
            / 1_000_000.0
        )
    )
    if specification.minimum_final_latency_ms is not None:
        if (
            final_latency_ms is None
            or final_latency_ms
            < specification.minimum_final_latency_ms
        ):
            return False
    if specification.maximum_final_latency_ms is not None:
        if (
            final_latency_ms is None
            or final_latency_ms
            > specification.maximum_final_latency_ms
        ):
            return False

    query = specification.text_query.casefold().strip()
    if not query:
        return True
    searchable = " ".join(
        [
            transaction.session_name,
            f"{transaction.request_service_id:02X}",
            transaction.request_service_name,
            transaction.status,
            record.automatic_correlation_label,
            transaction.request.payload_hex,
            (
                ""
                if transaction.first_response is None
                else transaction.first_response.payload_hex
            ),
            (
                ""
                if transaction.final_response is None
                else transaction.final_response.payload_hex
            ),
            (
                ""
                if transaction.final_negative_response_code
                is None
                else (
                    f"{transaction.final_negative_response_code:02X} "
                    f"{uds_nrc_name(transaction.final_negative_response_code)}"
                )
            ),
        ]
    ).casefold()
    return query in searchable


def _normalize_filter(
    value: UdsExplorerFilter,
) -> UdsExplorerFilter:
    start = _finite_optional(
        value.start_time_ms,
        "start_time_ms",
    )
    end = _finite_optional(
        value.end_time_ms,
        "end_time_ms",
    )
    minimum = _finite_optional(
        value.minimum_final_latency_ms,
        "minimum_final_latency_ms",
    )
    maximum = _finite_optional(
        value.maximum_final_latency_ms,
        "maximum_final_latency_ms",
    )
    if start is not None and start < 0:
        raise ValueError(
            "start_time_ms cannot be negative"
        )
    if end is not None and end < 0:
        raise ValueError(
            "end_time_ms cannot be negative"
        )
    if (
        start is not None
        and end is not None
        and start > end
    ):
        raise ValueError(
            "start_time_ms cannot exceed end_time_ms"
        )
    if minimum is not None and minimum < 0:
        raise ValueError(
            "minimum_final_latency_ms cannot be negative"
        )
    if maximum is not None and maximum < 0:
        raise ValueError(
            "maximum_final_latency_ms cannot be negative"
        )
    if (
        minimum is not None
        and maximum is not None
        and minimum > maximum
    ):
        raise ValueError(
            "minimum_final_latency_ms cannot exceed "
            "maximum_final_latency_ms"
        )

    return UdsExplorerFilter(
        session_ids=tuple(
            dict.fromkeys(
                str(item)
                for item in value.session_ids
                if str(item)
            )
        ),
        service_ids=tuple(
            dict.fromkeys(
                int(item)
                for item in value.service_ids
            )
        ),
        statuses=tuple(
            dict.fromkeys(
                str(item)
                for item in value.statuses
                if str(item)
            )
        ),
        negative_response_codes=tuple(
            dict.fromkeys(
                int(item)
                for item in value.negative_response_codes
            )
        ),
        text_query=str(value.text_query or "").strip(),
        start_time_ms=start,
        end_time_ms=end,
        minimum_final_latency_ms=minimum,
        maximum_final_latency_ms=maximum,
    )


def _finite_optional(
    value: float | None,
    label: str,
) -> float | None:
    if value is None:
        return None
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return converted


def _payload_bytes(value: str) -> bytes:
    compact = "".join(str(value or "").split())
    if not compact:
        return b""
    try:
        return bytes.fromhex(compact)
    except ValueError:
        return b""


def _message_details(message: Any) -> str:
    return (
        f"row={message.first_source_row}.."
        f"{message.last_source_row}, "
        f"t={message.first_timestamp_ns}.."
        f"{message.last_timestamp_ns}, "
        f"key={message.message_key}, "
        f"frames={message.frame_count}, "
        f"payload={message.payload_hex}"
    )


def _session_order(
    result: UdsLatencyResult,
    session_id: str,
) -> int:
    for index, item in enumerate(result.sessions):
        if item.session_id == session_id:
            return index
    return len(result.sessions)


def _percentile(
    values: Sequence[int],
    percentile: float,
) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    position = (
        (len(values) - 1)
        * percentile
        / 100.0
    )
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    fraction = position - lower
    return (
        values[lower] * (1.0 - fraction)
        + values[upper] * fraction
    )


def _percent_change(
    current: float | None,
    baseline: float | None,
) -> float | None:
    if (
        current is None
        or baseline is None
        or baseline == 0
    ):
        return None
    return (
        (current - baseline)
        / baseline
        * 100.0
    )


def _difference(
    current: float | None,
    baseline: float | None,
) -> float | None:
    if current is None or baseline is None:
        return None
    return current - baseline


def _number(value: float | None) -> str:
    return (
        ""
        if value is None
        else f"{value:.6f}"
    )


def _ms_number(
    value: float | int | None,
) -> str:
    return (
        ""
        if value is None
        else f"{float(value) / 1_000_000.0:.6f}"
    )


def _ms_text(
    value: float | int | None,
) -> str:
    return (
        "—"
        if value is None
        else f"{float(value) / 1_000_000.0:.3f} ms"
    )


def _hex_optional(
    value: int | None,
    width: int,
) -> str:
    return (
        ""
        if value is None
        else f"0x{value:0{width}X}"
    )


__all__ = [
    "GROUPING_MODES",
    "UdsExplorerFilter",
    "UdsLatencyDistribution",
    "UdsTransactionExplorerResult",
    "UdsTransactionGroup",
    "UdsTransactionGroupComparison",
    "UdsTransactionRecord",
    "build_uds_transaction_explorer",
    "export_groups_csv",
    "export_transactions_csv",
    "format_transaction_details",
]
