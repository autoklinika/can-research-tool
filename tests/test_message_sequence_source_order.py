from __future__ import annotations

from app.comparison_analysis_service import ComparisonAnalysisService
from app.comparison_sets import ComparisonSetStore
from app.extensions import MESSAGE_SEQUENCE_PROVIDER_ID
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter


def test_sequence_timestamps_follow_source_order_not_numeric_min_max(
    tmp_path,
) -> None:
    project = CrtProject.create(
        tmp_path / "project",
        name="Sequence source order",
    )
    frames = [
        _frame(0, 100, 0x100),
        _frame(1, 200, 0x200),
        _frame(2, 50, 0x100),
        _frame(3, 60, 0x200),
    ]
    before = _create_session(project, "before", frames)
    after = _create_session(project, "after", frames)
    comparison = ComparisonSetStore(project).create(
        name="Non-monotonic timestamps",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    service = ComparisonAnalysisService(project)

    result = service.run(
        MESSAGE_SEQUENCE_PROVIDER_ID,
        comparison.id,
        parameters={"memory_sequence_threshold": 1},
    )
    payload = service.artifacts.read_json(result.artifacts[0])
    sequence = next(
        item
        for item in payload["sequences"]
        if item["mode"] == "raw"
        and item["sequence_length"] == 2
        and item["sequence_text"].endswith(
            "0:STD:100:data → 0:STD:200:data"
        )
    )
    metrics = sequence["baseline"]

    assert metrics["occurrence_count"] == 2
    assert metrics["first_start_row"] == 0
    assert metrics["last_start_row"] == 2
    assert metrics["first_timestamp_ns"] == 100
    assert metrics["last_timestamp_ns"] == 50
    assert metrics["min_span_ns"] == 10
    assert metrics["mean_span_ns"] == 55.0
    assert metrics["max_span_ns"] == 100


def _frame(
    sequence: int,
    timestamp_ns: int,
    arbitration_id: int,
) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        arbitration_id=arbitration_id,
        data=bytes((sequence,)),
        channel=0,
        is_extended_id=False,
    )


def _create_session(
    project: CrtProject,
    name: str,
    frames: list[CanFrame],
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    capture = CaptureSession(
        name=name,
        source="test",
        bitrate=250_000,
        channel=0,
    )
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True})
    record = project.register_session(
        path,
        name=name,
        source="test",
        status="ready",
    )
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=0.0,
    )
    return project.session_by_path(path) or record
