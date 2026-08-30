from __future__ import annotations

from app.extensions.builtin import SIGNAL_DISCOVERY_PROVIDER_ID
from app.extensions.builtin.signal_discovery import (
    bitfield_series_from_sample,
    extract_bitfield,
)
from app.models import CanFrame, CaptureSession
from app.project import CrtProject
from app.session_analysis_service import SessionAnalysisService
from app.session_stream import SessionStreamWriter


def test_extract_bitfield_intel_uses_dbc_lsb_start_bit() -> None:
    payload = bytes((0x34, 0x12, 0xA5))

    assert extract_bitfield(payload, start_bit=0, length=16, byte_order="intel") == 0x1234
    assert extract_bitfield(payload, start_bit=4, length=8, byte_order="intel") == 0x23
    assert extract_bitfield(payload, start_bit=20, length=8, byte_order="intel") is None


def test_extract_bitfield_motorola_uses_candb_sawtooth_start_bit() -> None:
    payload = bytes((0x12, 0x34, 0x80))

    assert extract_bitfield(payload, start_bit=7, length=16, byte_order="motorola") == 0x1234
    assert extract_bitfield(payload, start_bit=23, length=8, byte_order="motorola", signed=True) == -128
    # CANdb++ saw-tooth semantics: after bit 0 the next bit is bit 7 of the
    # following byte, therefore start_bit=0,length=9 is valid for this payload.
    assert extract_bitfield(payload, start_bit=0, length=9, byte_order="motorola") == 0x34
    # Starting at bit 0 of the final byte would need to jump to a non-existent
    # fourth byte for the second bit.
    assert extract_bitfield(payload, start_bit=16, length=2, byte_order="motorola") is None


def test_bitfield_series_preserves_exact_source_rows_and_scaling() -> None:
    frames = (
        {"source_row": 7, "sequence": 10, "timestamp_ns": 1_000, "data": [0x10, 0x00]},
        {"source_row": 18, "sequence": 21, "timestamp_ns": 2_000, "data": [0x20, 0x00]},
    )

    series = bitfield_series_from_sample(
        frames,
        start_bit=0,
        length=8,
        byte_order="intel",
        signed=False,
        scale=0.5,
        offset=-1.0,
    )

    assert [point["source_row"] for point in series] == [7, 18]
    assert [point["raw"] for point in series] == [0x10, 0x20]
    assert [point["value"] for point in series] == [7.0, 15.0]


def test_provider_builds_exact_activity_and_bounded_evidence(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Signal discovery")
    session = _write_session(
        project,
        (
            _frame(0, 0x200, b"\xAA\x55"),
            _frame(1, 0x123, b"\x00\x10"),
            _frame(2, 0x201, b"\xBB"),
            _frame(3, 0x123, b"\x01"),
            _frame(4, 0x123, b"\x03\x30"),
        ),
    )
    service = SessionAnalysisService(project)

    result = service.run(
        SIGNAL_DISCOVERY_PROVIDER_ID,
        session.id,
        parameters={
            "channel": 0,
            "arbitration_id": "0x123",
            "is_extended_id": False,
            "frame_kind": "data",
            "sample_limit": 2,
        },
    )
    artifact = result.artifacts[0]
    payload = service.artifacts.read_json(artifact)

    assert artifact.artifact_type == "signal_discovery_activity"
    assert payload["message_key"]["arbitration_id"] == 0x123
    assert payload["summary"]["matching_frame_count"] == 3
    assert payload["summary"]["first_source_row"] == 1
    assert payload["summary"]["last_source_row"] == 4
    assert payload["summary"]["min_dlc"] == 1
    assert payload["summary"]["max_dlc"] == 2
    assert payload["summary"]["variable_dlc"] is True

    byte0 = payload["bytes"][0]
    assert byte0["present_count"] == 3
    assert byte0["missing_count"] == 0
    assert byte0["min_value"] == 0
    assert byte0["max_value"] == 3
    assert byte0["unique_value_count"] == 3
    assert byte0["transition_opportunity_count"] == 2
    assert byte0["change_count"] == 2
    assert byte0["change_rate"] == 1.0
    assert byte0["min_source_row"] == 1
    assert byte0["max_source_row"] == 4
    assert byte0["bits"][0]["set_count"] == 2
    assert byte0["bits"][0]["transition_count"] == 1
    assert byte0["bits"][0]["transition_opportunity_count"] == 2
    assert byte0["bits"][0]["transition_rate"] == 0.5
    assert byte0["bits"][1]["set_count"] == 1
    assert byte0["bits"][1]["transition_count"] == 1

    byte1 = payload["bytes"][1]
    assert byte1["present_count"] == 2
    assert byte1["missing_count"] == 1
    # The missing middle byte breaks continuity, so 0x10 -> 0x30 is not counted
    # as a transition between adjacent observations of the byte and there is no
    # transition opportunity at all for this byte in the example.
    assert byte1["transition_opportunity_count"] == 0
    assert byte1["change_count"] == 0
    assert byte1["change_rate"] is None
    assert byte1["bits"][5]["transition_rate"] is None

    sample = payload["sample"]
    assert sample["bounded"] is True
    assert sample["sampled_frame_count"] == 2
    assert [frame["source_row"] for frame in sample["frames"]] == [1, 4]
    assert [frame["data_hex"] for frame in sample["frames"]] == ["00 10", "03 30"]


def test_provider_keeps_extended_and_standard_keys_separate(tmp_path) -> None:
    project = CrtProject.create(tmp_path / "project", name="Exact key")
    session = _write_session(
        project,
        (
            _frame(0, 0x123, b"\x01", extended=False),
            _frame(1, 0x123, b"\x02", extended=True),
        ),
    )
    service = SessionAnalysisService(project)

    artifact = service.run(
        SIGNAL_DISCOVERY_PROVIDER_ID,
        session.id,
        parameters={
            "channel": 0,
            "arbitration_id": 0x123,
            "is_extended_id": True,
            "frame_kind": "data",
        },
    ).artifacts[0]
    payload = service.artifacts.read_json(artifact)

    assert payload["summary"]["matching_frame_count"] == 1
    assert payload["summary"]["first_source_row"] == 1
    assert payload["bytes"][0]["first_value"] == 2


def _frame(
    sequence: int,
    arbitration_id: int,
    data: bytes,
    *,
    extended: bool = False,
) -> CanFrame:
    return CanFrame(
        sequence=sequence,
        timestamp_ns=sequence * 1_000_000,
        arbitration_id=arbitration_id,
        data=data,
        channel=0,
        is_extended_id=extended,
    )


def _write_session(project: CrtProject, frames: tuple[CanFrame, ...]):
    path = project.live_sessions_dir / "signal-discovery.crt.jsonl"
    capture = CaptureSession(name="signal-discovery", source="test", bitrate=250_000, channel=0)
    writer = SessionStreamWriter(capture, path)
    writer.open()
    for frame in frames:
        writer.append(frame)
    writer.close({"clean_close": True})
    record = project.register_session(
        path,
        name="signal-discovery",
        source="test",
        status="ready",
    )
    project.finalize_session(
        path,
        frame_count=len(frames),
        marker_count=0,
        duration_s=(frames[-1].timestamp_ns - frames[0].timestamp_ns) / 1e9 if frames else 0.0,
    )
    return project.session_by_path(path) or record
