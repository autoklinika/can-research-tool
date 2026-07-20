from __future__ import annotations

from app.filters import FilterMode, FilterPreset
from app.logical_records import LogicalMessageRecord
from app.static_active_filters import StaticCombinedActiveFilterSet


def test_can_id_pattern_is_raw_only_in_logical_message_view() -> None:
    preset = FilterPreset.create("Raw CAN mask")
    preset.mode = FilterMode.INCLUDE
    preset.root = {
        "type": "condition",
        "field": "can_id",
        "operator": "can_id_pattern",
        "values": ["0x18DA??00"],
    }
    filters = StaticCombinedActiveFilterSet([preset])
    message = LogicalMessageRecord(
        sequence=1,
        first_timestamp_ns=0,
        last_timestamp_ns=1_000,
        protocol="uds",
        transport="isotp",
        name="ReadDataByIdentifier",
        arbitration_id=0x18DAF900,
        is_extended_id=True,
        pgn=None,
        source_address=None,
        destination_address=None,
        complete=True,
        frame_sequences=(1,),
        payload=bytes.fromhex("62 F1 90"),
    )

    decision = filters.decide_logical_message(message)

    assert decision.visible is True
    assert decision.unavailable_reasons == (
        "Raw CAN mask: warunek niedostępny w tym kontekście",
    )
