from __future__ import annotations

from pathlib import Path

import pytest

from app.comparison_evidence import (
    locate_comparison_evidence,
    parse_message_key,
)
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.project_search_index import ProjectSearchIndex
from app.session_stream import SessionStreamWriter


def test_locates_evidence_with_fallback_and_persistent_index(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Evidence")
    session = _create_session(project)

    fallback = locate_comparison_evidence(
        project,
        session.id,
        "0:STD:100:data",
    )
    assert fallback.source_row == 0
    assert fallback.session_path == project.absolute_path(session.relative_path)

    ProjectSearchIndex(project).rebuild_session(project, session)
    indexed = locate_comparison_evidence(
        project,
        session.id,
        "1:EXT:18DAF900:remote",
    )
    assert indexed.source_row == 2


def test_rejects_invalid_or_missing_evidence(tmp_path: Path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Evidence")
    session = _create_session(project)

    with pytest.raises(ValueError):
        parse_message_key("not-a-message-key")
    with pytest.raises(LookupError):
        locate_comparison_evidence(
            project,
            session.id,
            "0:STD:555:data",
        )


def _create_session(project: CrtProject):
    path = project.live_sessions_dir / "evidence.crt.jsonl"
    frames = (
        CanFrame(0, 0, 0x100, b"\x01", channel=0),
        CanFrame(1, 1_000_000, 0x200, b"\x02", channel=0),
        CanFrame(
            2,
            2_000_000,
            0x18DAF900,
            b"",
            channel=1,
            is_extended_id=True,
            is_remote_frame=True,
        ),
    )
    capture = CaptureSession(
        name="evidence",
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
        name="evidence",
        source="test",
        status="ready",
    )
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=0.002,
    )
    return project.session_by_path(path) or record
