from __future__ import annotations

from pathlib import Path

from app.comparison_sets import ComparisonSetStore
from app.comparison_uds_explorer_source import (
    load_preferred_uds_latency_source,
)
from app.comparison_uds_latency import ComparisonUdsLatencyService
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter

REQUEST_ID = 0x18DA30F9
RESPONSE_ID = 0x18DAF930
REQUEST_KEY = "0:EXT:18DA30F9:data"
RESPONSE_KEY = "0:EXT:18DAF930:data"
EMPTY_REQUEST_KEY = "0:EXT:18DA31F9:data"
EMPTY_RESPONSE_KEY = "0:EXT:18DAF931:data"


def test_prefers_older_nonempty_artifact_over_newer_empty_one(
    tmp_path: Path,
) -> None:
    project, comparison = _project_with_uds_sessions(tmp_path)
    service = ComparisonUdsLatencyService(project)

    useful = service.run_and_save(
        comparison,
        REQUEST_KEY,
        RESPONSE_KEY,
        timeout_ms=1_000.0,
    )
    empty = service.run_and_save(
        comparison,
        EMPTY_REQUEST_KEY,
        EMPTY_RESPONSE_KEY,
        timeout_ms=1_000.0,
    )
    assert empty.artifact.id != useful.artifact.id
    assert sum(
        len(session.transaction_evidence)
        for session in empty.result.sessions
    ) == 0

    selected = load_preferred_uds_latency_source(service, comparison)

    assert selected.stored is not None
    assert selected.stored.artifact.id == useful.artifact.id
    assert selected.evidence_count == 2
    assert selected.skipped_newer_empty_artifacts == 1


def test_returns_latest_empty_artifact_when_no_evidence_exists(
    tmp_path: Path,
) -> None:
    project, comparison = _project_with_uds_sessions(tmp_path)
    service = ComparisonUdsLatencyService(project)
    empty = service.run_and_save(
        comparison,
        EMPTY_REQUEST_KEY,
        EMPTY_RESPONSE_KEY,
        timeout_ms=1_000.0,
    )

    selected = load_preferred_uds_latency_source(service, comparison)

    assert selected.stored is not None
    assert selected.stored.artifact.id == empty.artifact.id
    assert selected.evidence_count == 0
    assert selected.skipped_newer_empty_artifacts == 0


def _project_with_uds_sessions(tmp_path: Path):
    project = CrtProject.create(tmp_path / "project", name="UDS source selection")
    before = _create_session(project, "before", response_delay_ns=10_000_000)
    after = _create_session(project, "after", response_delay_ns=20_000_000)
    comparison = ComparisonSetStore(project).create(
        name="Before versus after",
        session_ids=(before.id, after.id),
        base_session_id=before.id,
    )
    return project, comparison


def _create_session(
    project: CrtProject,
    name: str,
    *,
    response_delay_ns: int,
):
    path = project.live_sessions_dir / f"{name}.crt.jsonl"
    frames = [
        CanFrame(
            0,
            0,
            REQUEST_ID,
            _single_frame(b"\x22\xF1\x90"),
            channel=0,
            is_extended_id=True,
        ),
        CanFrame(
            1,
            response_delay_ns,
            RESPONSE_ID,
            _single_frame(b"\x62\xF1\x90\x12"),
            channel=0,
            is_extended_id=True,
        ),
    ]
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
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=response_delay_ns / 1_000_000_000.0,
    )
    record = project.session_by_path(path)
    if record is None:
        raise AssertionError(f"session was not registered: {path}")
    return record


def _single_frame(payload: bytes) -> bytes:
    return bytes([len(payload)]) + payload
