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
    STATUS_CHANGED,
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

    fallback_error = locate_comparison_evidence(
        project,
        session.id,
        "0:STD:321:error",
    )
    assert fallback_error.source_row == 3

    ProjectSearchIndex(project).rebuild_session(project, session)
    indexed = locate_comparison_evidence(
        project,
        session.id,
        "1:EXT:18DAF900:remote",
    )
    assert indexed.source_row == 2

    indexed_error = locate_comparison_evidence(
        project,
        session.id,
        "0:STD:321:error",
    )
    assert indexed_error.source_row == 3


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
            _statistics_key("0:STD:10:data", "10", ("after",)),
            _statistics_key("0:STD:100:data", "100", ("after",)),
        ],
    }
    sequence = {
        "schema": SCHEMA_SEQUENCE,
        "sessions": sessions,
        "summary": {"notable_change_count": 1},
        "ranked_changes": [
            {
                "session_id": "after",
                "sequence_text": "0:STD:100:data → 0:STD:200:data",
            }
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


def test_dashboard_uses_complete_sequence_matrix_per_compared_session() -> None:
    sessions = [
        {"id": "before", "name": "Przed", "role": "base"},
        {"id": "after-a", "name": "Po A", "role": "compared"},
        {"id": "after-b", "name": "Po B", "role": "compared"},
    ]
    compared_ids = ("after-a", "after-b")
    statistics = {
        "schema": SCHEMA_STATISTICS,
        "sessions": sessions,
        "message_keys": [
            _statistics_key("0:STD:100:data", "100", compared_ids),
            _statistics_key("0:STD:200:data", "200", compared_ids),
            _statistics_key("0:STD:300:data", "300", compared_ids),
        ],
    }
    sequence = {
        "schema": SCHEMA_SEQUENCE,
        "sessions": sessions,
        "summary": {
            "notable_change_count": 2,
            "returned_notable_change_count": 1,
            "notable_changes_truncated": True,
            "matrix_complete": True,
        },
        "sequences": [
            _sequence_matrix_row(
                ("0:STD:100:data", "0:STD:200:data"),
                changed_session_id="after-a",
                sessions=sessions,
            ),
            _sequence_matrix_row(
                ("0:STD:200:data", "0:STD:300:data"),
                changed_session_id="after-b",
                sessions=sessions,
            ),
        ],
        "ranked_changes": [
            {
                "session_id": "after-a",
                "sequence_text": "0:STD:100:data → 0:STD:200:data",
            }
        ],
    }

    data = build_dashboard_data(
        "Complete sequence matrix",
        {SCHEMA_STATISTICS: statistics, SCHEMA_SEQUENCE: sequence},
    )
    rows = {(row.session_id, row.message_key): row for row in data.rows}
    assert rows[("after-a", "0:STD:100:data")].sequence_change_count == 1
    assert rows[("after-a", "0:STD:300:data")].sequence_change_count == 0
    assert rows[("after-b", "0:STD:100:data")].sequence_change_count == 0
    assert rows[("after-b", "0:STD:300:data")].sequence_change_count == 1
    assert rows[("after-a", "0:STD:100:data")].status == STATUS_CHANGED
    assert rows[("after-b", "0:STD:300:data")].status == STATUS_CHANGED


def _statistics_key(
    message_key: str,
    arbitration_id_hex: str,
    compared_ids: tuple[str, ...],
) -> dict:
    metrics = {"frame_count": 1, "mean_positive_frequency_hz": 1.0}
    sessions = [
        {
            "session_id": "before",
            "session_name": "Przed",
            "role": "base",
            "statistics": metrics,
            "change": {"reasons": []},
        }
    ]
    sessions.extend(
        {
            "session_id": session_id,
            "session_name": session_id,
            "role": "compared",
            "statistics": metrics,
            "change": {"reasons": []},
        }
        for session_id in compared_ids
    )
    return {
        "message_key": message_key,
        "channel": 0,
        "arbitration_id_hex": arbitration_id_hex,
        "is_extended_id": False,
        "frame_kind": "data",
        "baseline": metrics,
        "sessions": sessions,
    }


def _sequence_matrix_row(
    message_keys: tuple[str, ...],
    *,
    changed_session_id: str,
    sessions: list[dict],
) -> dict:
    return {
        "sequence_text": " → ".join(message_keys),
        "sequence": [{"message_key": key} for key in message_keys],
        "sessions": [
            {
                "session_id": session["id"],
                "session_name": session["name"],
                "role": session["role"],
                "change": {
                    "reasons": (
                        ["occurrence_increase"]
                        if session["id"] == changed_session_id
                        else []
                    )
                },
            }
            for session in sessions
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
        CanFrame(
            3,
            3_000_000,
            0x321,
            b"",
            channel=0,
            is_error_frame=True,
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
        duration_s=0.003,
    )
    return project.session_by_path(path) or record
