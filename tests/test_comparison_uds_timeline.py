from __future__ import annotations

from types import SimpleNamespace

from app.comparison_timeline import ComparisonTimelineLane, ComparisonTimelineResult
from app.comparison_uds_explorer_source import PreferredUdsLatencySource
from app.comparison_uds_latency import (
    StoredUdsLatency,
    UdsLatencyConfiguration,
    UdsLatencyResult,
    UdsMessageEvidence,
    UdsSessionLatencyStatistics,
    UdsTransactionEvidence,
)
from app.comparison_uds_timeline import (
    UdsTimelineFilter,
    UdsTimelineSources,
    build_uds_timeline,
)


REQUEST_KEY = "0:EXT:18DA30F9:data"
RESPONSE_KEY = "0:EXT:18DAF930:data"


def test_projects_transactions_on_saved_alignment_and_compares_sequences() -> None:
    baseline = _session(
        "before",
        "Before",
        (
            _transaction("before", "Before", 0, 100_000_000, b"\x22\xF1\x90", b"\x62\xF1\x90", pending=True),
            _transaction("before", "Before", 3, 300_000_000, b"\x31\x01\xF0\x22", b"\x71\x01\xF0\x22"),
        ),
    )
    compared = _session(
        "after",
        "After",
        (
            _transaction("after", "After", 0, 1_300_000_000, b"\x31\x01\xF0\x22", b"\x71\x01\xF0\x22"),
            _transaction("after", "After", 2, 1_500_000_000, b"\x22\xF1\x90", b"\x7F\x22\x31", status="negative-response", nrc=0x31),
            _transaction("after", "After", 4, 1_700_000_000, b"\x19\x02\xFF", None, status="timeout"),
        ),
    )
    sources = _sources((baseline, compared))

    result = build_uds_timeline(sources)

    assert result.alignment_artifact_id == "alignment-artifact"
    assert result.uds_artifact_id == "uds-artifact"
    assert result.skipped_newer_empty_uds_artifacts == 1
    assert [lane.session_id for lane in result.lanes] == ["before", "after"]
    assert result.lanes[0].transactions[0].request_relative_time_ns == 100_000_000
    assert result.lanes[1].transactions[0].request_relative_time_ns == 300_000_000
    assert result.lanes[0].transactions[0].pending_relative_times_ns == (110_000_000,)

    after_labels = [
        item.sequence_classification for item in result.lanes[1].transactions
    ]
    assert after_labels == ["shifted", "matched", "additional"]
    difference = result.differences[0]
    assert difference.session_id == "after"
    assert difference.missing_count == 0
    assert difference.additional_count == 1
    assert difference.shifted_count == 1


def test_filters_did_status_nrc_and_visible_session_without_losing_baseline_comparison() -> None:
    baseline = _session(
        "before",
        "Before",
        (_transaction("before", "Before", 0, 100_000_000, b"\x22\xF1\x90", b"\x62\xF1\x90"),),
    )
    compared = _session(
        "after",
        "After",
        (
            _transaction(
                "after",
                "After",
                0,
                1_100_000_000,
                b"\x22\xF1\x90",
                b"\x7F\x22\x31",
                status="negative-response",
                nrc=0x31,
            ),
            _transaction("after", "After", 2, 1_400_000_000, b"\x31\x01\xF0\x22", None, status="timeout"),
        ),
    )
    result = build_uds_timeline(
        _sources((baseline, compared)),
        filter_specification=UdsTimelineFilter(
            session_ids=("after",),
            service_ids=(0x22,),
            statuses=("negative-response",),
            dids=(0xF190,),
            negative_response_codes=(0x31,),
            text_query="F190",
        ),
    )

    assert [lane.session_id for lane in result.lanes] == ["after"]
    assert result.visible_transaction_count == 1
    item = result.lanes[0].transactions[0]
    assert item.record.did == 0xF190
    assert item.transaction.final_negative_response_code == 0x31
    assert item.sequence_classification == "matched"


def _sources(sessions: tuple[UdsSessionLatencyStatistics, ...]) -> UdsTimelineSources:
    lanes = (
        _lane("before", "Before", 0),
        _lane("after", "After", 1_000_000_000),
    )
    alignment = SimpleNamespace(
        artifact=SimpleNamespace(id="alignment-artifact"),
        result=ComparisonTimelineResult(
            synchronization_mode="session_start",
            anchor_message_key="",
            lanes=lanes,
            warnings=(),
            minimum_relative_time_ns=0,
            maximum_relative_time_ns=2_000_000_000,
        ),
    )
    latency = UdsLatencyResult(
        configuration=UdsLatencyConfiguration(REQUEST_KEY, RESPONSE_KEY),
        baseline_session_id="before",
        sessions=sessions,
        comparisons=(),
        warnings=(),
    )
    preferred = PreferredUdsLatencySource(
        stored=StoredUdsLatency(
            artifact=SimpleNamespace(id="uds-artifact"),
            result=latency,
        ),
        evidence_count=sum(len(item.transaction_evidence) for item in sessions),
        skipped_newer_empty_artifacts=1,
    )
    return UdsTimelineSources(alignment=alignment, uds=preferred)


def _lane(session_id: str, name: str, anchor_ns: int) -> ComparisonTimelineLane:
    return ComparisonTimelineLane(
        session_id=session_id,
        session_name=name,
        total_frame_count=20,
        sampled_frame_count=20,
        sample_stride=1,
        anchor_source_row=0,
        anchor_timestamp_ns=anchor_ns,
        first_timestamp_ns=anchor_ns,
        last_timestamp_ns=anchor_ns + 2_000_000_000,
        synchronized=True,
        warning="",
        events=(),
        anchor_kind="session_start",
        anchor_label="Początek sesji",
    )


def _session(
    session_id: str,
    name: str,
    transactions: tuple[UdsTransactionEvidence, ...],
) -> UdsSessionLatencyStatistics:
    completed = sum(item.status in {"positive-response", "negative-response"} for item in transactions)
    return UdsSessionLatencyStatistics(
        session_id=session_id,
        session_name=name,
        request_message_key=REQUEST_KEY,
        response_message_key=RESPONSE_KEY,
        request_count=len(transactions),
        completed_count=completed,
        positive_response_count=sum(item.status == "positive-response" for item in transactions),
        negative_response_count=sum(item.status == "negative-response" for item in transactions),
        timeout_count=sum(item.status == "timeout" for item in transactions),
        capture_ended_count=0,
        suppressed_no_response_count=0,
        response_pending_transaction_count=sum(item.response_pending_count > 0 for item in transactions),
        response_pending_count=sum(item.response_pending_count for item in transactions),
        unmatched_response_count=0,
        incomplete_isotp_message_count=0,
        completion_rate_percent=(100.0 * completed / len(transactions)) if transactions else None,
        mean_first_response_latency_ns=None,
        p50_first_response_latency_ns=None,
        p95_first_response_latency_ns=None,
        p99_first_response_latency_ns=None,
        mean_final_response_latency_ns=None,
        p50_final_response_latency_ns=None,
        p95_final_response_latency_ns=None,
        p99_final_response_latency_ns=None,
        first_latency_sample_count=completed,
        final_latency_sample_count=completed,
        transaction_evidence=transactions,
        unmatched_responses=(),
        evidence_truncated=False,
    )


def _transaction(
    session_id: str,
    session_name: str,
    source_row: int,
    timestamp_ns: int,
    request_payload: bytes,
    response_payload: bytes | None,
    *,
    status: str = "positive-response",
    nrc: int | None = None,
    pending: bool = False,
) -> UdsTransactionEvidence:
    request = _message(
        session_id,
        session_name,
        REQUEST_KEY,
        source_row,
        timestamp_ns,
        request_payload,
        request_payload[0],
    )
    pending_message = (
        _message(
            session_id,
            session_name,
            RESPONSE_KEY,
            source_row + 1,
            timestamp_ns + 10_000_000,
            b"\x7F" + request_payload[:1] + b"\x78",
            0x7F,
            requested_service_id=request_payload[0],
            nrc=0x78,
            response_pending=True,
        )
        if pending
        else None
    )
    final = (
        None
        if response_payload is None
        else _message(
            session_id,
            session_name,
            RESPONSE_KEY,
            source_row + (2 if pending else 1),
            timestamp_ns + (40_000_000 if pending else 20_000_000),
            response_payload,
            response_payload[0],
            requested_service_id=(request_payload[0] if response_payload[0] == 0x7F else None),
            nrc=nrc,
        )
    )
    first = pending_message or final
    return UdsTransactionEvidence(
        session_id=session_id,
        session_name=session_name,
        request_service_id=request_payload[0],
        request_service_name=f"SID 0x{request_payload[0]:02X}",
        status=status,
        request=request,
        first_response=first,
        final_response=final,
        pending_responses=() if pending_message is None else (pending_message,),
        response_pending_count=1 if pending else 0,
        first_response_latency_ns=(None if first is None else first.first_timestamp_ns - timestamp_ns),
        final_response_latency_ns=(None if final is None else final.last_timestamp_ns - timestamp_ns),
        final_negative_response_code=nrc,
        suppress_positive_response=False,
    )


def _message(
    session_id: str,
    session_name: str,
    message_key: str,
    source_row: int,
    timestamp_ns: int,
    payload: bytes,
    service_id: int,
    *,
    requested_service_id: int | None = None,
    nrc: int | None = None,
    response_pending: bool = False,
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
        payload_hex=payload.hex(" ").upper(),
        service_id=service_id,
        service_name=f"SID 0x{service_id:02X}",
        requested_service_id=requested_service_id,
        negative_response_code=nrc,
        negative_response_name="",
        response_pending=response_pending,
        complete=True,
    )
