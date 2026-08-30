from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.comparison_uds_latency import (
    UdsLatencyConfiguration,
    UdsLatencyResult,
    UdsMessageEvidence,
    UdsSessionLatencyStatistics,
    UdsTransactionEvidence,
)
from app.comparison_uds_transaction_explorer import (
    UdsExplorerFilter,
    build_uds_transaction_explorer,
    export_groups_csv,
    export_transactions_csv,
    format_transaction_details,
)

REQUEST_KEY = "0:EXT:18DA30F9:data"
RESPONSE_KEY = "0:EXT:18DAF930:data"


def test_extracts_protocol_correlation_and_filters() -> None:
    result = _latency_result()
    explorer = build_uds_transaction_explorer(
        result,
        source_artifact_id="artifact-1",
    )

    assert explorer.source_artifact_id == "artifact-1"
    assert explorer.source_transaction_count == 5
    assert len(explorer.visible_transactions) == 5

    by_row = {
        item.transaction.request.first_source_row: item
        for item in explorer.visible_transactions
    }
    assert by_row[0].did == 0xF190
    assert by_row[0].automatic_correlation_key == "sid:22:did:F190"
    assert by_row[10].subfunction == 0x01
    assert by_row[10].routine_id == 0xF022
    assert "Routine 0xF022" in by_row[10].automatic_correlation_label
    assert by_row[20].subfunction == 0x02

    filtered = build_uds_transaction_explorer(
        result,
        filter_specification=UdsExplorerFilter(
            session_ids=("after",),
            service_ids=(0x31,),
            statuses=("timeout",),
            text_query="f022",
            start_time_ms=9.0,
            end_time_ms=20.0,
        ),
        grouping_mode="routine",
    )
    assert len(filtered.visible_transactions) == 1
    record = filtered.visible_transactions[0]
    assert record.transaction.session_id == "after"
    assert record.routine_id == 0xF022
    assert record.transaction.status == "timeout"

    negative = build_uds_transaction_explorer(
        result,
        filter_specification=UdsExplorerFilter(
            negative_response_codes=(0x31,),
            text_query="requestOutOfRange",
        ),
    )
    assert len(negative.visible_transactions) == 1
    assert negative.visible_transactions[0].transaction.request_service_id == 0x19


def test_builds_group_metrics_and_baseline_comparisons() -> None:
    explorer = build_uds_transaction_explorer(
        _latency_result(),
        grouping_mode="service",
    )

    groups = {
        (item.session_id, item.group_key): item
        for item in explorer.groups
    }
    before_22 = groups[("before", "sid:22")]
    after_22 = groups[("after", "sid:22")]
    assert before_22.transaction_count == 1
    assert before_22.positive_response_count == 1
    assert before_22.completion_rate_percent == 100.0
    assert after_22.transaction_count == 1
    assert after_22.p50_final_response_latency_ns == 25_000_000

    before_31 = groups[("before", "sid:31")]
    after_31 = groups[("after", "sid:31")]
    assert before_31.response_pending_count == 1
    assert before_31.p50_first_response_latency_ns == 5_000_000
    assert before_31.p50_final_response_latency_ns == 30_000_000
    assert after_31.timeout_count == 1
    assert after_31.completion_rate_percent == 0.0

    comparison = next(
        item
        for item in explorer.comparisons
        if item.session_id == "after" and item.group_key == "sid:31"
    )
    assert comparison.transaction_count_delta == 0
    assert comparison.completion_rate_delta_percentage_points == -100.0
    assert comparison.timeout_count_delta == 1
    assert comparison.response_pending_count_delta == -1

    distributions = {
        item.session_id: item
        for item in explorer.distributions
    }
    assert distributions["before"].transaction_count == 3
    assert distributions["after"].transaction_count == 2
    assert distributions["before"].p95_final_response_latency_ns is not None


def test_latency_filter_and_invalid_ranges() -> None:
    result = _latency_result()
    filtered = build_uds_transaction_explorer(
        result,
        filter_specification=UdsExplorerFilter(
            minimum_final_latency_ms=26.0,
            maximum_final_latency_ms=31.0,
        ),
    )
    assert len(filtered.visible_transactions) == 1
    assert filtered.visible_transactions[0].routine_id == 0xF022

    with pytest.raises(ValueError, match="start_time_ms"):
        build_uds_transaction_explorer(
            result,
            filter_specification=UdsExplorerFilter(
                start_time_ms=10.0,
                end_time_ms=2.0,
            ),
        )

    with pytest.raises(ValueError, match="grouping mode"):
        build_uds_transaction_explorer(
            result,
            grouping_mode="unknown",
        )


def test_warns_when_stage2c2_evidence_is_truncated() -> None:
    result = _latency_result(truncated=True)
    explorer = build_uds_transaction_explorer(result)
    assert explorer.warnings
    assert "bounded" in explorer.warnings[0]
    assert "before" in explorer.warnings[0]


def test_formats_details_and_exports_semicolon_csv(tmp_path: Path) -> None:
    explorer = build_uds_transaction_explorer(
        _latency_result(),
        grouping_mode="auto",
    )
    routine = next(
        item
        for item in explorer.visible_transactions
        if item.routine_id == 0xF022
        and item.transaction.session_id == "before"
    )
    details = format_transaction_details(routine)
    assert "Routine 0xF022" in details
    assert "31 01 F0 22" in details
    assert "7F 31 78" in details
    assert "71 01 F0 22" in details

    transactions_path = export_transactions_csv(
        tmp_path / "transactions.csv",
        explorer.visible_transactions,
    )
    groups_path = export_groups_csv(
        tmp_path / "groups.csv",
        explorer.groups,
    )
    assert transactions_path.exists()
    assert groups_path.exists()

    with transactions_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows[0][0] == "session_id"
    assert len(rows) == 6
    routine_row = next(row for row in rows[1:] if row[8] == "0x01")
    assert routine_row[9] == "0xF022"
    assert routine_row[14] == "31 01 F0 22"

    with groups_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        group_rows = list(csv.reader(handle, delimiter=";"))
    assert group_rows[0][0] == "grouping_mode"
    assert any("DID 0xF190" in row[2] for row in group_rows[1:])


def _latency_result(*, truncated: bool = False) -> UdsLatencyResult:
    before_transactions = (
        _transaction(
            session_id="before",
            session_name="before",
            request_row=0,
            request_time_ns=0,
            request_payload=b"\x22\xF1\x90",
            status="positive-response",
            first_payload=b"\x62\xF1\x90\x12",
            first_time_ns=20_000_000,
            final_payload=b"\x62\xF1\x90\x12",
            final_time_ns=20_000_000,
        ),
        _transaction(
            session_id="before",
            session_name="before",
            request_row=10,
            request_time_ns=10_000_000,
            request_payload=b"\x31\x01\xF0\x22",
            status="positive-response",
            first_payload=b"\x7F\x31\x78",
            first_time_ns=15_000_000,
            final_payload=b"\x71\x01\xF0\x22",
            final_time_ns=40_000_000,
            pending=True,
        ),
        _transaction(
            session_id="before",
            session_name="before",
            request_row=20,
            request_time_ns=20_000_000,
            request_payload=b"\x19\x02\xFF",
            status="negative-response",
            first_payload=b"\x7F\x19\x31",
            first_time_ns=28_000_000,
            final_payload=b"\x7F\x19\x31",
            final_time_ns=28_000_000,
            nrc=0x31,
        ),
    )
    after_transactions = (
        _transaction(
            session_id="after",
            session_name="after",
            request_row=0,
            request_time_ns=0,
            request_payload=b"\x22\xF1\x90",
            status="positive-response",
            first_payload=b"\x62\xF1\x90\x34",
            first_time_ns=25_000_000,
            final_payload=b"\x62\xF1\x90\x34",
            final_time_ns=25_000_000,
        ),
        _transaction(
            session_id="after",
            session_name="after",
            request_row=10,
            request_time_ns=10_000_000,
            request_payload=b"\x31\x01\xF0\x22",
            status="timeout",
        ),
    )
    configuration = UdsLatencyConfiguration(
        request_message_key=REQUEST_KEY,
        response_message_key=RESPONSE_KEY,
        timeout_ms=5_000.0,
    )
    return UdsLatencyResult(
        configuration=configuration,
        baseline_session_id="before",
        sessions=(
            _session_statistics(
                "before",
                before_transactions,
                evidence_truncated=truncated,
            ),
            _session_statistics(
                "after",
                after_transactions,
            ),
        ),
        comparisons=(),
        warnings=(),
    )


def _session_statistics(
    session_id: str,
    transactions: tuple[UdsTransactionEvidence, ...],
    *,
    evidence_truncated: bool = False,
) -> UdsSessionLatencyStatistics:
    positive = sum(item.status == "positive-response" for item in transactions)
    negative = sum(item.status == "negative-response" for item in transactions)
    timeout = sum(item.status == "timeout" for item in transactions)
    completed = positive + negative
    pending_transactions = sum(
        item.response_pending_count > 0 for item in transactions
    )
    pending_count = sum(item.response_pending_count for item in transactions)
    first = [
        item.first_response_latency_ns
        for item in transactions
        if item.first_response_latency_ns is not None
    ]
    final = [
        item.final_response_latency_ns
        for item in transactions
        if item.final_response_latency_ns is not None
    ]
    return UdsSessionLatencyStatistics(
        session_id=session_id,
        session_name=session_id,
        request_message_key=REQUEST_KEY,
        response_message_key=RESPONSE_KEY,
        request_count=len(transactions),
        completed_count=completed,
        positive_response_count=positive,
        negative_response_count=negative,
        timeout_count=timeout,
        capture_ended_count=0,
        suppressed_no_response_count=0,
        response_pending_transaction_count=pending_transactions,
        response_pending_count=pending_count,
        unmatched_response_count=0,
        incomplete_isotp_message_count=0,
        completion_rate_percent=(completed / len(transactions) * 100.0),
        mean_first_response_latency_ns=(
            sum(first) / len(first) if first else None
        ),
        p50_first_response_latency_ns=(
            float(sorted(first)[len(first) // 2]) if first else None
        ),
        p95_first_response_latency_ns=(max(first) if first else None),
        p99_first_response_latency_ns=(max(first) if first else None),
        mean_final_response_latency_ns=(
            sum(final) / len(final) if final else None
        ),
        p50_final_response_latency_ns=(
            float(sorted(final)[len(final) // 2]) if final else None
        ),
        p95_final_response_latency_ns=(max(final) if final else None),
        p99_final_response_latency_ns=(max(final) if final else None),
        first_latency_sample_count=len(first),
        final_latency_sample_count=len(final),
        transaction_evidence=transactions,
        unmatched_responses=(),
        evidence_truncated=evidence_truncated,
        warning="",
    )


def _transaction(
    *,
    session_id: str,
    session_name: str,
    request_row: int,
    request_time_ns: int,
    request_payload: bytes,
    status: str,
    first_payload: bytes | None = None,
    first_time_ns: int | None = None,
    final_payload: bytes | None = None,
    final_time_ns: int | None = None,
    pending: bool = False,
    nrc: int | None = None,
) -> UdsTransactionEvidence:
    sid = request_payload[0]
    request = _message(
        session_id=session_id,
        session_name=session_name,
        message_key=REQUEST_KEY,
        source_row=request_row,
        timestamp_ns=request_time_ns,
        payload=request_payload,
        service_id=sid,
    )
    first = (
        None
        if first_payload is None or first_time_ns is None
        else _message(
            session_id=session_id,
            session_name=session_name,
            message_key=RESPONSE_KEY,
            source_row=request_row + 1,
            timestamp_ns=first_time_ns,
            payload=first_payload,
            service_id=first_payload[0],
            requested_service_id=(sid if first_payload[0] == 0x7F else None),
            nrc=(first_payload[2] if first_payload[0] == 0x7F else None),
        )
    )
    final = (
        None
        if final_payload is None or final_time_ns is None
        else _message(
            session_id=session_id,
            session_name=session_name,
            message_key=RESPONSE_KEY,
            source_row=request_row + (2 if pending else 1),
            timestamp_ns=final_time_ns,
            payload=final_payload,
            service_id=final_payload[0],
            requested_service_id=(sid if final_payload[0] == 0x7F else None),
            nrc=(final_payload[2] if final_payload[0] == 0x7F else None),
        )
    )
    pending_responses = (first,) if pending and first is not None else ()
    return UdsTransactionEvidence(
        session_id=session_id,
        session_name=session_name,
        request_service_id=sid,
        request_service_name={0x22: "ReadDataByIdentifier", 0x31: "RoutineControl", 0x19: "ReadDTCInformation"}[sid],
        status=status,
        request=request,
        first_response=first,
        final_response=final,
        pending_responses=pending_responses,
        response_pending_count=1 if pending else 0,
        first_response_latency_ns=(
            None if first is None else first.first_timestamp_ns - request.last_timestamp_ns
        ),
        final_response_latency_ns=(
            None if final is None else final.first_timestamp_ns - request.last_timestamp_ns
        ),
        final_negative_response_code=nrc,
        suppress_positive_response=False,
    )


def _message(
    *,
    session_id: str,
    session_name: str,
    message_key: str,
    source_row: int,
    timestamp_ns: int,
    payload: bytes,
    service_id: int,
    requested_service_id: int | None = None,
    nrc: int | None = None,
) -> UdsMessageEvidence:
    return UdsMessageEvidence(
        session_id=session_id,
        session_name=session_name,
        message_key=message_key,
        first_source_row=source_row,
        last_source_row=source_row,
        first_timestamp_ns=timestamp_ns,
        last_timestamp_ns=timestamp_ns,
        frame_count=1,
        payload_hex=" ".join(f"{byte:02X}" for byte in payload),
        service_id=service_id,
        service_name="",
        requested_service_id=requested_service_id,
        negative_response_code=nrc,
        negative_response_name=("" if nrc is None else "requestOutOfRange"),
        response_pending=nrc == 0x78,
        complete=True,
        error="",
    )
