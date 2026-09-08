from __future__ import annotations

import hashlib

import pytest

from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_stream import SessionStreamWriter
from app.signal_plot_service import SignalPlotService, cursor_delta, decimate_for_render, nearest_point_index


def test_full_signal_series_preserves_every_matching_point_and_source_row(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Full signal plotter")
    session, path = _write_session(
        project,
        (
            _frame(0, 0x200, b"\x99"),
            _frame(1, 0x123, b"\x10\x00"),
            _frame(2, 0x123, b"\x20\x00"),
            _frame(3, 0x201, b"\x77"),
            _frame(4, 0x123, b"\x30\x00"),
            _frame(5, 0x123, b"\x40\x00"),
        ),
    )
    source_sha = _sha256(path)
    service = SignalPlotService(project)

    artifact = service.run(
        session.id,
        parameters={
            "channel": 0,
            "arbitration_id": "0x123",
            "is_extended_id": False,
            "frame_kind": "data",
            "start_bit": 0,
            "length": 8,
            "byte_order": "intel",
            "signed": False,
            "scale": 0.5,
            "offset": -1.0,
            "maximum_points": 100,
        },
    ).artifacts[0]
    payload = service.read_series(artifact)

    assert artifact.artifact_type == "signal_plot_series"
    assert payload["schema"] == "crt.signal_plot_series"
    assert payload["series_contract"]["complete"] is True
    assert payload["series_contract"]["sampling"] == "none"
    assert payload["series_contract"]["cursor_selection_uses_full_series"] is True
    assert payload["summary"]["matching_frame_count"] == 4
    assert payload["summary"]["point_count"] == 4
    assert payload["summary"]["field_missing_count"] == 0
    assert [point["source_row"] for point in payload["points"]] == [1, 2, 4, 5]
    assert [point["raw"] for point in payload["points"]] == [0x10, 0x20, 0x30, 0x40]
    assert [point["value"] for point in payload["points"]] == [7.0, 15.0, 23.0, 31.0]
    assert _sha256(path) == source_sha


def test_full_signal_series_rejects_limit_without_partial_artifact(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Full plot limit")
    session, path = _write_session(
        project,
        tuple(_frame(index, 0x123, bytes((index,))) for index in range(5)),
    )
    source_sha = _sha256(path)
    service = SignalPlotService(project)

    with pytest.raises(ValueError, match="no partial artifact"):
        service.run(
            session.id,
            parameters={
                "channel": 0,
                "arbitration_id": "123",
                "is_extended_id": False,
                "frame_kind": "data",
                "start_bit": 0,
                "length": 8,
                "maximum_points": 3,
            },
        )

    assert service.list_artifacts(session.id) == ()
    assert _sha256(path) == source_sha


def test_full_signal_series_counts_missing_field_without_inventing_values(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Missing bitfield")
    session, _path = _write_session(
        project,
        (
            _frame(0, 0x123, b"\x01\x02"),
            _frame(1, 0x123, b"\x03"),
            _frame(2, 0x123, b"\x04\x05"),
        ),
    )
    service = SignalPlotService(project)
    artifact = service.run(
        session.id,
        parameters={
            "channel": 0,
            "arbitration_id": "0x123",
            "is_extended_id": False,
            "frame_kind": "data",
            "start_bit": 8,
            "length": 8,
            "byte_order": "intel",
            "maximum_points": 100,
        },
    ).artifacts[0]
    payload = service.read_series(artifact)

    assert payload["summary"]["matching_frame_count"] == 3
    assert payload["summary"]["point_count"] == 2
    assert payload["summary"]["field_missing_count"] == 1
    assert [point["source_row"] for point in payload["points"]] == [0, 2]
    assert [point["raw"] for point in payload["points"]] == [2, 5]


def test_cursor_helpers_use_exact_full_series_points() -> None:
    points = (
        {"timestamp_ns": 100, "value": 1.0, "source_row": 10},
        {"timestamp_ns": 250, "value": 4.0, "source_row": 20},
        {"timestamp_ns": 900, "value": 2.0, "source_row": 30},
    )

    assert nearest_point_index(points, 90) == 0
    assert nearest_point_index(points, 200) == 1
    assert nearest_point_index(points, 700) == 2
    delta = cursor_delta(points[0], points[2])
    assert delta.delta_time_ns == 800
    assert delta.delta_value == 1.0


def test_render_decimation_preserves_endpoints_and_extrema_without_mutating_source() -> None:
    points = tuple(
        {"timestamp_ns": index, "value": float(value), "source_row": index}
        for index, value in enumerate((0, 1, 9, 2, -8, 3, 7, 4, 5, 6, 0))
    )
    original_rows = [point["source_row"] for point in points]

    rendered = decimate_for_render(points, 8)

    assert len(rendered) <= 8
    assert rendered[0] is points[0]
    assert rendered[-1] is points[-1]
    assert any(point["value"] == 9.0 for point in rendered)
    assert any(point["value"] == -8.0 for point in rendered)
    assert [point["source_row"] for point in points] == original_rows


def _frame(sequence: int, arbitration_id: int, data: bytes) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=(sequence + 1) * 100_000_000,
        arbitration_id=arbitration_id,
        data=data,
        channel=0,
        is_extended_id=False,
    )


def _write_session(project: CrtProject, frames: tuple[CanFrame, ...]):
    path = project.live_sessions_dir / "full-signal-plotter.crt.jsonl"
    capture = CaptureSession(name="full-signal-plotter", source="test", bitrate=250_000, channel=0)
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True, "frame_count": len(frames)})
    record = project.register_session(
        path,
        name="full-signal-plotter",
        source="test",
        status="ready",
    )
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=(frames[-1].timestamp_ns - frames[0].timestamp_ns) / 1e9 if frames else 0.0,
    )
    return project.session_by_path(path) or record, path


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
