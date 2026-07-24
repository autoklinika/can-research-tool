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
from gui.comparison_visualization_model import (
    SCHEMA_SEQUENCE,
    SCHEMA_STATISTICS,
    build_dashboard_data,
    optional_hex_int,
)


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
    with pytest.raises(ValueError):
        parse_message_key("0:STD:800:data")
    parsed = parse_message_key("0:EXT:1FFFFFFF:data")
    assert parsed.arbitration_id == 0x1FFFFFFF
    assert parsed.is_extended_id

    with pytest.raises(LookupError, match="Nie znaleziono klucza wiadomości"):
        locate_comparison_evidence(
            project,
            session.id,
            "0:STD:555:data",
        )


def test_dashboard_sequence_matching_is_exact_and_hex_sort_values_are_safe() -> None:
    sessions = [
        {"id": "before", "name": "Przed", "role": "base"},
        {"id": "after", "name": "Po", "role": "compared"},
    ]
    statistics = {
        "schema": SCHEMA_STATISTICS,
        "sessions": sessions,
        "message_keys": [
            _statistics_key("0:STD:10:data", "10"),
            _statistics_key("0:STD:100:data", "100"),
        ],
    }
    sequence = {
        "schema": SCHEMA_SEQUENCE,
        "sessions": sessions,
        "summary": {"notable_change_count": 1},
        "ranked_changes": [
            {"sequence_text": "0:STD:100:data → 0:STD:200:data"}
        ],
    }

    data = build_dashboard_data(
        "Exact sequence matching",
        {SCHEMA_STATISTICS: statistics, SCHEMA_SEQUENCE: sequence},
    )
    counts = {row.message_key: row.sequence_change_count for row in data.rows}
    assert counts["0:STD:10:data"] == 0
    assert counts["0:STD:100:data"] == 1
    assert optional_hex_int("—") is None
    assert optional_hex_int("not-hex") is None
    assert optional_hex_int("18DAF900") == 0x18DAF900


def _statistics_key(message_key: str, arbitration_id_hex: str) -> dict:
    metrics = {"frame_count": 1, "mean_positive_frequency_hz": 1.0}
    return {
        "message_key": message_key,
        "channel": 0,
        "arbitration_id_hex": arbitration_id_hex,
        "is_extended_id": False,
        "frame_kind": "data",
        "baseline": metrics,
        "sessions": [
            {
                "session_id": "before",
                "session_name": "Przed",
                "role": "base",
                "statistics": metrics,
                "change": {"reasons": []},
            },
            {
                "session_id": "after",
                "session_name": "Po",
                "role": "compared",
                "statistics": metrics,
                "change": {"reasons": []},
            },
        ],
    }


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
