from __future__ import annotations

import pytest

from app.filters import FilterCompiler, MatchState
from app.isotp_filters import (
    IsoTpAddressing,
    IsoTpCompletion,
    IsoTpFilterSpec,
    IsoTpFraming,
)
from app.logical_records import LogicalMessageRecord
from app.models import CanFrame
from app.protocols import ProtocolRegistry
from app.stream_pipeline import StreamingTransportPipeline


def _record_from_frames(*frames: CanFrame) -> LogicalMessageRecord:
    pipeline = StreamingTransportPipeline()
    messages = pipeline.feed_many(frames)
    assert len(messages) == 1
    return LogicalMessageRecord.from_decoded(ProtocolRegistry().decode(messages[0]))


def test_11bit_single_frame_profile_matches_complete_uds_request() -> None:
    record = _record_from_frames(
        CanFrame(
            sequence=1,
            timestamp_ns=1_000_000,
            arbitration_id=0x7E0,
            is_extended_id=False,
            data=bytes.fromhex("03 22 F1 90 00 00 00 00"),
        )
    )
    preset = IsoTpFilterSpec(
        addressing=IsoTpAddressing.NORMAL_11BIT,
        framing=IsoTpFraming.SINGLE_FRAME,
        completion=IsoTpCompletion.COMPLETE,
        has_error=False,
        can_ids=(0x7E0,),
        min_declared_payload_length=3,
        max_declared_payload_length=3,
        min_received_payload_length=3,
        max_received_payload_length=3,
        min_source_frame_count=1,
        max_source_frame_count=1,
    ).to_preset("11-bit UDS request")

    assert FilterCompiler().validate(preset) == []
    assert FilterCompiler().evaluate_logical_message(preset, record).state is MatchState.MATCH


def test_29bit_multiframe_profile_matches_reassembled_response_and_addresses() -> None:
    record = _record_from_frames(
        CanFrame(
            sequence=10,
            timestamp_ns=1_000_000,
            arbitration_id=0x18DAF930,
            is_extended_id=True,
            data=bytes.fromhex("10 0A 62 F1 90 31 32 33"),
        ),
        CanFrame(
            sequence=11,
            timestamp_ns=2_000_000,
            arbitration_id=0x18DAF930,
            is_extended_id=True,
            data=bytes.fromhex("21 34 35 36 37 38 39 3A"),
        ),
    )
    preset = IsoTpFilterSpec(
        addressing=IsoTpAddressing.NORMAL_FIXED_29BIT,
        framing=IsoTpFraming.MULTI_FRAME,
        completion=IsoTpCompletion.COMPLETE,
        has_error=False,
        source_addresses=(0x30,),
        destination_addresses=(0xF9,),
        min_declared_payload_length=10,
        max_declared_payload_length=10,
        min_received_payload_length=10,
        max_received_payload_length=10,
        min_source_frame_count=2,
    ).to_preset("29-bit multiframe response")

    assert FilterCompiler().evaluate_logical_message(preset, record).state is MatchState.MATCH


def test_sequence_mismatch_profile_matches_incomplete_isotp_error() -> None:
    record = _record_from_frames(
        CanFrame(
            sequence=20,
            timestamp_ns=1_000_000,
            arbitration_id=0x18DAF930,
            is_extended_id=True,
            data=bytes.fromhex("10 0A 62 F1 90 31 32 33"),
        ),
        CanFrame(
            sequence=21,
            timestamp_ns=2_000_000,
            arbitration_id=0x18DAF930,
            is_extended_id=True,
            data=bytes.fromhex("22 34 35 36 37 38 39 3A"),
        ),
    )
    preset = IsoTpFilterSpec(
        addressing=IsoTpAddressing.NORMAL_FIXED_29BIT,
        framing=IsoTpFraming.MULTI_FRAME,
        completion=IsoTpCompletion.INCOMPLETE,
        has_error=True,
        min_declared_payload_length=10,
        max_declared_payload_length=10,
        max_received_payload_length=6,
    ).to_preset("Broken ISO-TP sequence")

    assert record.complete is False
    assert "sequence mismatch" in record.error
    assert FilterCompiler().evaluate_logical_message(preset, record).state is MatchState.MATCH


def test_isotp_profile_does_not_match_raw_transport_record() -> None:
    record = LogicalMessageRecord(
        sequence=30,
        first_timestamp_ns=1_000_000,
        last_timestamp_ns=1_000_000,
        protocol="unknown",
        transport="raw",
        name="Unknown",
        arbitration_id=0x7E0,
        is_extended_id=False,
        pgn=None,
        source_address=None,
        destination_address=None,
        complete=True,
        frame_sequences=(30,),
        payload=bytes.fromhex("03 22 F1 90"),
        fields={},
    )
    preset = IsoTpFilterSpec().to_preset("Only ISO-TP")

    assert FilterCompiler().evaluate_logical_message(preset, record).state is MatchState.NO_MATCH


@pytest.mark.parametrize(
    "spec",
    [
        IsoTpFilterSpec(can_ids=(0x20000000,)),
        IsoTpFilterSpec(source_addresses=(0x100,)),
        IsoTpFilterSpec(min_declared_payload_length=10, max_declared_payload_length=5),
        IsoTpFilterSpec(min_source_frame_count=0),
    ],
)
def test_invalid_isotp_profile_is_rejected_before_preset_creation(
    spec: IsoTpFilterSpec,
) -> None:
    with pytest.raises(ValueError):
        spec.to_preset("Invalid")
