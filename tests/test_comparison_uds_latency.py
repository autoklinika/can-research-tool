from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.comparison_sets import ComparisonSetStore
from app.comparison_uds_latency import (
    ComparisonUdsLatencyService,
    StaleUdsLatencyArtifact,
    UDS_LATENCY_ARTIFACT_TYPE,
    UdsLatencyConfiguration,
    analyze_comparison_uds_latency,
    uds_latency_result_from_payload,
    uds_latency_result_to_payload,
)
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter

REQUEST_ID = 0x18DA30F9
RESPONSE_ID = 0x18DAF930
REQUEST_KEY = "0:EXT:18DA30F9:data"
RESPONSE_KEY = "0:EXT:18DAF930:data"


def test_pairs_positive_negative_pending_and_timeout_transactions(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="UDS latency")
    before = _create_session(
        project,
        "before",
        [
            _frame(0, 0, REQUEST_ID, _sf(b"\x22\xF1\x90")),
            _frame(1, 10_000_000, RESPONSE_ID, _sf(b"\x7F\x22\x78")),
            _frame(
                2,
                40_000_000,
                RESPONSE_ID,
                _sf(b"\x62\xF1\x90\x12"),
            ),
            _frame(3, 100_000_000, REQUEST_ID, _sf(b"\x10\x01")),
            _frame(4, 120_000_000, RESPONSE_ID, _sf(b"\x50\x01")),
            _frame(5, 130_000_000, RESPONSE_ID, _sf(b"\x51\x01")),
        ],
    )
    after = _create_session(
        project,
        "after",
        [
            _frame(0, 0, REQUEST_ID, _sf(b"\x22\xF1\x90")),
            _frame(
                1,
                70_000_000,
                RESPONSE_ID,
                _sf(b"\x62\xF1\x90\x34"),
            ),
            _frame(2, 100_000_000, REQUEST_ID, _sf(b"\x10\x01")),
            _frame(3, 2_000_000_000, 0x123, b"\x00"),
        ],
    )
    comparison = ComparisonSetStore(project).create(
        name="Before versus after",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )

    result = analyze_comparison_uds_latency(
        project,
        comparison,
        UdsLatencyConfiguration(
            request_message_key=REQUEST_KEY,
            response_message_key=RESPONSE_KEY,
            timeout_ms=1_000.0,
        ),
    )

    before_stats, after_stats = result.sessions
    assert before_stats.request_count == 2
    assert before_stats.completed_count == 2
    assert before_stats.positive_response_count == 2
    assert before_stats.response_pending_transaction_count == 1
    assert before_stats.response_pending_count == 1
    assert before_stats.unmatched_response_count == 1
    assert before_stats.timeout_count == 0
    assert before_stats.p50_first_response_latency_ns == pytest.approx(
        15_000_000.0
    )
    assert before_stats.p50_final_response_latency_ns == pytest.approx(
        30_000_000.0
    )

    first = before_stats.transaction_evidence[0]
    assert first.request_service_id == 0x22
    assert first.status == "positive-response"
    assert first.request.first_source_row == 0
    assert first.first_response is not None
    assert first.first_response.first_source_row == 1
    assert first.final_response is not None
    assert first.final_response.first_source_row == 2
    assert first.first_response_latency_ns == 10_000_000
    assert first.final_response_latency_ns == 40_000_000
    assert first.response_pending_count == 1

    assert after_stats.request_count == 2
    assert after_stats.completed_count == 1
    assert after_stats.timeout_count == 1
    assert after_stats.capture_ended_count == 0
    assert after_stats.p50_final_response_latency_ns == 70_000_000
    assert result.comparisons[0].timeout_count_delta == 1
    assert result.comparisons[0].completion_rate_delta_percentage_points == -50.0


def test_negative_response_and_suppress_positive_response_are_classified(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="UDS status")
    before = _create_session(
        project,
        "before",
        [
            _frame(0, 0, REQUEST_ID, _sf(b"\x27\x01")),
            _frame(1, 5_000_000, RESPONSE_ID, _sf(b"\x7F\x27\x35")),
            _frame(2, 10_000_000, REQUEST_ID, _sf(b"\x3E\x80")),
            _frame(3, 2_000_000_000, 0x123, b"\x00"),
        ],
    )
    after = _create_session(
        project,
        "after",
        [_frame(0, 0, REQUEST_ID, _sf(b"\x3E\x80"))],
    )
    comparison = ComparisonSetStore(project).create(
        name="Status",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )

    result = analyze_comparison_uds_latency(
        project,
        comparison,
        UdsLatencyConfiguration(
            request_message_key=REQUEST_KEY,
            response_message_key=RESPONSE_KEY,
            timeout_ms=1_000.0,
        ),
    )

    before_stats = result.sessions[0]
    assert before_stats.negative_response_count == 1
    assert before_stats.suppressed_no_response_count == 1
    negative = next(
        item
        for item in before_stats.transaction_evidence
        if item.status == "negative-response"
    )
    assert negative.final_negative_response_code == 0x35
    suppressed = next(
        item
        for item in before_stats.transaction_evidence
        if item.status == "suppressed-no-response"
    )
    assert suppressed.suppress_positive_response


def test_multiframe_response_preserves_first_and_last_source_rows(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="UDS multi")
    response_payload = b"\x62\xF1\x90ABCDEFGHIJ"
    first_frame, consecutive = _multiframe(response_payload)
    before = _create_session(
        project,
        "before",
        [
            _frame(0, 0, REQUEST_ID, _sf(b"\x22\xF1\x90")),
            _frame(1, 10_000_000, RESPONSE_ID, first_frame),
            _frame(2, 12_000_000, RESPONSE_ID, consecutive),
        ],
    )
    after = _create_session(
        project,
        "after",
        [
            _frame(0, 0, REQUEST_ID, _sf(b"\x22\xF1\x90")),
            _frame(1, 20_000_000, RESPONSE_ID, first_frame),
            _frame(2, 22_000_000, RESPONSE_ID, consecutive),
        ],
    )
    comparison = ComparisonSetStore(project).create(
        name="Multi",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )

    result = analyze_comparison_uds_latency(
        project,
        comparison,
        UdsLatencyConfiguration(
            request_message_key=REQUEST_KEY,
            response_message_key=RESPONSE_KEY,
        ),
    )

    response = result.sessions[0].transaction_evidence[0].final_response
    assert response is not None
    assert response.first_source_row == 1
    assert response.last_source_row == 2
    assert response.frame_count == 2
    assert result.sessions[0].p50_final_response_latency_ns == 10_000_000


def test_uds_latency_artifact_round_trips_and_rejects_changed_fingerprint(
    tmp_path: Path,
) -> None:
    project = CrtProject.create(tmp_path / "project", name="UDS artifact")
    before = _create_session(
        project,
        "before",
        [
            _frame(0, 0, REQUEST_ID, _sf(b"\x10\x01")),
            _frame(1, 20_000_000, RESPONSE_ID, _sf(b"\x50\x01")),
        ],
    )
    after = _create_session(
        project,
        "after",
        [
            _frame(0, 0, REQUEST_ID, _sf(b"\x10\x01")),
            _frame(1, 30_000_000, RESPONSE_ID, _sf(b"\x50\x01")),
        ],
    )
    comparison = ComparisonSetStore(project).create(
        name="Artifact",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )

    service = ComparisonUdsLatencyService(project)
    execution = service.run_and_save(
        comparison,
        REQUEST_KEY,
        RESPONSE_KEY,
    )
    stored = service.load_latest_compatible(
        comparison,
        request_message_key=REQUEST_KEY,
        response_message_key=RESPONSE_KEY,
    )

    assert execution.artifact.artifact_type == UDS_LATENCY_ARTIFACT_TYPE
    assert stored is not None
    assert stored.artifact.id == execution.artifact.id
    assert stored.result == execution.result

    records_by_id = {record.id: record for record in project.list_sessions()}
    records = tuple(records_by_id[item] for item in comparison.session_ids)
    payload = uds_latency_result_to_payload(
        comparison,
        execution.result,
        records=records,
    )
    changed = deepcopy(payload)
    changed["session_fingerprints"][0]["frame_count"] += 1
    with pytest.raises(
        StaleUdsLatencyArtifact,
        match="frame count changed",
    ):
        uds_latency_result_from_payload(
            changed,
            comparison_set=comparison,
            records=records,
        )


def _create_session(
    project: CrtProject,
    name: str,
    frames: list[CanFrame],
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    writer = SessionStreamWriter(
        CaptureSession(
            name=name,
            source="test",
            bitrate=250_000,
            channel=0,
        ),
        path,
    )
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True})
    project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
    duration_s = (
        (frames[-1].timestamp_ns - frames[0].timestamp_ns) / 1_000_000_000.0
        if len(frames) > 1
        else 0.0
    )
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=duration_s,
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(f"session was not registered: {path}")
    return record


def _frame(
    sequence: int,
    timestamp_ns: int,
    arbitration_id: int,
    data: bytes,
) -> CanFrame:
    return CanFrame(
        sequence,
        timestamp_ns,
        arbitration_id,
        data,
        channel=0,
        is_extended_id=arbitration_id > 0x7FF,
    )


def _sf(payload: bytes) -> bytes:
    if len(payload) > 15:
        raise ValueError("test single frame payload is too long")
    return bytes([len(payload)]) + payload


def _multiframe(payload: bytes) -> tuple[bytes, bytes]:
    if not 7 < len(payload) <= 13:
        raise ValueError("test payload must fit one FF and one CF")
    first = bytes([0x10 | ((len(payload) >> 8) & 0x0F), len(payload)]) + payload[:6]
    consecutive = b"\x21" + payload[6:]
    return first, consecutive
