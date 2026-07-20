from __future__ import annotations

from app.filters import FilterMode, FilterPreset
from app.models import CanFrame
from app.static_active_filters import StaticCombinedActiveFilterSet
from app.static_filter_patterns import CanIdPattern, PayloadPattern
from app.static_frame_adapter import static_frame_record


def test_static_raw_hot_path_uses_only_precompiled_values(monkeypatch) -> None:
    preset = FilterPreset.create("Fast static")
    preset.mode = FilterMode.INCLUDE
    preset.root = {
        "type": "group",
        "operator": "and",
        "children": [
            {
                "type": "condition",
                "field": "can_id",
                "operator": "can_id_pattern",
                "values": ["0x18DA??00"],
            },
            {
                "type": "condition",
                "field": "payload",
                "operator": "payload_prefix",
                "values": ["62 F1 ??"],
            },
            {
                "type": "condition",
                "field": "dlc",
                "operator": "between",
                "values": ["3", "8"],
            },
            {
                "type": "condition",
                "field": "channel",
                "operator": "eq",
                "values": ["1"],
            },
        ],
    }
    filters = StaticCombinedActiveFilterSet([preset])

    def fail(*_args, **_kwargs):
        raise AssertionError("raw hot path must not parse or normalize preset values")

    monkeypatch.setattr(CanIdPattern, "parse", fail)
    monkeypatch.setattr(PayloadPattern, "parse", fail)
    monkeypatch.setattr(filters._legacy_compiler, "_normalize_value", fail)

    for sequence in range(20_000):
        frame = CanFrame(
            sequence=sequence,
            timestamp_ns=sequence * 1_000,
            arbitration_id=0x18DAF900,
            data=bytes.fromhex("62 F1 90"),
            channel=1,
            is_extended_id=True,
        )
        assert filters.decide(static_frame_record(frame)).visible is True
