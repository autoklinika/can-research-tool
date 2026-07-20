from __future__ import annotations

import pytest

from app.filters import FilterCompiler, MatchState
from app.logical_records import LogicalMessageRecord
from app.message_models import TransportKind, TransportMessage
from app.protocols import ProtocolRegistry
from app.uds_filters import (
    UdsDirection,
    UdsFilterSpec,
    UdsSecurityAccessPhase,
    UdsService,
)


def _record(
    payload: bytes,
    *,
    arbitration_id: int = 0x18DAF110,
    extended: bool = True,
    source: int | None = 0x10,
    destination: int | None = 0xF1,
    complete: bool = True,
    frame_sequences: tuple[int, ...] = (1,),
    error: str = "",
) -> LogicalMessageRecord:
    message = TransportMessage(
        sequence=1,
        first_timestamp_ns=1_000_000,
        last_timestamp_ns=2_000_000,
        transport=TransportKind.ISOTP,
        payload=payload,
        frame_sequences=frame_sequences,
        arbitration_id=arbitration_id,
        is_extended_id=extended,
        source_address=source,
        destination_address=destination,
        complete=complete,
        error=error,
        metadata={"declared_payload_length": len(payload)},
    )
    return LogicalMessageRecord.from_decoded(ProtocolRegistry().decode(message))


def _evaluate(spec: UdsFilterSpec, record: LogicalMessageRecord) -> MatchState:
    preset = spec.to_preset("UDS test")
    compiler = FilterCompiler()
    assert compiler.validate(preset) == []
    return compiler.evaluate_logical_message(preset, record).state


def test_read_data_positive_response_filters_service_direction_and_did() -> None:
    record = _record(bytes.fromhex("62 F1 90 31 32 33"))
    spec = UdsFilterSpec.for_service(
        UdsService.READ_DATA_BY_IDENTIFIER,
        direction=UdsDirection.POSITIVE_RESPONSE,
        dids=(0xF190,),
        min_payload_length=6,
        max_payload_length=6,
        can_ids=(0x18DAF110,),
        source_addresses=(0x10,),
        destination_addresses=(0xF1,),
        complete=True,
    )

    assert _evaluate(spec, record) is MatchState.MATCH


def test_negative_response_filters_requested_service_and_nrc() -> None:
    record = _record(bytes.fromhex("7F 27 35"))
    spec = UdsFilterSpec.negative_responses(
        services=(UdsService.SECURITY_ACCESS,),
        nrcs=(0x35,),
    )

    assert _evaluate(spec, record) is MatchState.MATCH

    wrong_nrc = UdsFilterSpec.negative_responses(
        services=(UdsService.SECURITY_ACCESS,),
        nrcs=(0x33,),
    )
    assert _evaluate(wrong_nrc, record) is MatchState.NO_MATCH


def test_nrc_without_direction_automatically_selects_negative_response() -> None:
    record = _record(bytes.fromhex("7F 36 78"))
    spec = UdsFilterSpec(services=(UdsService.TRANSFER_DATA,), nrcs=(0x78,))
    preset = spec.to_preset("Pending TransferData")

    direction_nodes = [
        node
        for node in preset.root["children"]
        if node.get("field") == "direction"
    ]

    assert direction_nodes[0]["values"] == ["negative-response"]
    assert FilterCompiler().evaluate_logical_message(preset, record).state is MatchState.MATCH


def test_security_access_seed_and_key_profiles_use_level_subfunctions() -> None:
    seed = _record(bytes.fromhex("27 05"))
    key = _record(bytes.fromhex("27 06 12 34"))

    seed_spec = UdsFilterSpec(
        services=(UdsService.SECURITY_ACCESS,),
        directions=(UdsDirection.REQUEST,),
        security_access_phase=UdsSecurityAccessPhase.REQUEST_SEED,
        security_levels=(3,),
    )
    key_spec = UdsFilterSpec(
        services=(UdsService.SECURITY_ACCESS,),
        directions=(UdsDirection.REQUEST,),
        security_access_phase=UdsSecurityAccessPhase.SEND_KEY,
        security_levels=(3,),
    )

    assert _evaluate(seed_spec, seed) is MatchState.MATCH
    assert _evaluate(seed_spec, key) is MatchState.NO_MATCH
    assert _evaluate(key_spec, key) is MatchState.MATCH
    assert _evaluate(key_spec, seed) is MatchState.NO_MATCH


def test_security_level_without_phase_matches_seed_and_key() -> None:
    seed = _record(bytes.fromhex("27 05"))
    key = _record(bytes.fromhex("27 06 12 34"))
    spec = UdsFilterSpec(security_levels=(3,))

    assert _evaluate(spec, seed) is MatchState.MATCH
    assert _evaluate(spec, key) is MatchState.MATCH


@pytest.mark.parametrize(
    ("service", "payload"),
    [
        (UdsService.REQUEST_DOWNLOAD, "34 00 44 00 00 00 10"),
        (UdsService.REQUEST_UPLOAD, "35 00 44 00 00 00 10"),
        (UdsService.TRANSFER_DATA, "36 01 AA BB"),
        (UdsService.TESTER_PRESENT, "3E 00"),
        (UdsService.ECU_RESET, "11 01"),
        (UdsService.READ_DTC_INFORMATION, "19 02"),
    ],
)
def test_named_service_profiles_match_requests(service: UdsService, payload: str) -> None:
    record = _record(bytes.fromhex(payload))
    spec = UdsFilterSpec.for_service(service, direction=UdsDirection.REQUEST)

    assert _evaluate(spec, record) is MatchState.MATCH


def test_routine_control_filters_subfunction_and_routine_id() -> None:
    record = _record(bytes.fromhex("31 01 12 34"))
    spec = UdsFilterSpec.for_service(
        UdsService.ROUTINE_CONTROL,
        direction=UdsDirection.REQUEST,
        subfunctions=(0x01,),
        routine_ids=(0x1234,),
    )

    assert _evaluate(spec, record) is MatchState.MATCH


def test_raw_sid_can_distinguish_request_from_positive_response() -> None:
    request = _record(bytes.fromhex("22 F1 90"))
    response = _record(bytes.fromhex("62 F1 90 31"))
    request_spec = UdsFilterSpec(sids=(0x22,))
    response_spec = UdsFilterSpec(sids=(0x62,))

    assert _evaluate(request_spec, request) is MatchState.MATCH
    assert _evaluate(request_spec, response) is MatchState.NO_MATCH
    assert _evaluate(response_spec, response) is MatchState.MATCH


def test_non_uds_record_is_rejected_by_protocol_guard() -> None:
    record = LogicalMessageRecord(
        sequence=9,
        first_timestamp_ns=1,
        last_timestamp_ns=1,
        protocol="unknown",
        transport="raw",
        name="Unknown",
        arbitration_id=0x123,
        is_extended_id=False,
        pgn=None,
        source_address=None,
        destination_address=None,
        complete=True,
        frame_sequences=(9,),
        payload=bytes.fromhex("22 F1 90"),
        fields={},
    )
    spec = UdsFilterSpec.for_service(UdsService.READ_DATA_BY_IDENTIFIER)

    assert _evaluate(spec, record) is MatchState.NO_MATCH


@pytest.mark.parametrize(
    "spec",
    [
        UdsFilterSpec(sids=(0x100,)),
        UdsFilterSpec(nrcs=(-1,)),
        UdsFilterSpec(dids=(0x1_0000,)),
        UdsFilterSpec(routine_ids=(0x1_0000,)),
        UdsFilterSpec(security_levels=(0,)),
        UdsFilterSpec(min_payload_length=10, max_payload_length=5),
        UdsFilterSpec(
            services=(UdsService.TESTER_PRESENT,),
            security_access_phase=UdsSecurityAccessPhase.REQUEST_SEED,
        ),
        UdsFilterSpec(
            services=(UdsService.ECU_RESET,),
            routine_ids=(0x1234,),
        ),
        UdsFilterSpec(
            directions=(UdsDirection.REQUEST,),
            nrcs=(0x31,),
        ),
    ],
)
def test_invalid_uds_profiles_are_rejected(spec: UdsFilterSpec) -> None:
    with pytest.raises(ValueError):
        spec.to_preset("Invalid")
