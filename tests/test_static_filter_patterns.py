from __future__ import annotations

import pytest

from app.static_filter_patterns import (
    CAN_ID_MAX,
    CanIdPattern,
    PatternParseError,
    PayloadMatchMode,
    PayloadPattern,
)


def test_exact_can_id_pattern_matches_only_one_identifier() -> None:
    pattern = CanIdPattern.parse("0x18DAF900")

    assert pattern.mask == CAN_ID_MAX
    assert pattern.matches(0x18DAF900)
    assert not pattern.matches(0x18DA00F9)


def test_wildcard_can_id_pattern_matches_selected_nibbles() -> None:
    pattern = CanIdPattern.parse("0x18DA??F9")

    assert pattern.value == 0x18DA00F9
    assert pattern.mask == 0x1FFF00FF
    assert pattern.matches(0x18DA00F9)
    assert pattern.matches(0x18DAF9F9)
    assert not pattern.matches(0x18DB00F9)


def test_explicit_can_id_mask_is_canonicalized() -> None:
    pattern = CanIdPattern.parse("0x18DA55F9/0x1FFF00FF")

    assert pattern.value == 0x18DA00F9
    assert pattern.mask == 0x1FFF00FF
    assert pattern.matches(0x18DAAAF9)


def test_can_id_pattern_rejects_values_outside_classic_can_range() -> None:
    with pytest.raises(PatternParseError):
        CanIdPattern.parse("0x20000000")


def test_payload_exact_pattern_supports_wildcard_bytes() -> None:
    pattern = PayloadPattern.parse("62 F1 ??")

    assert pattern.matches(bytes.fromhex("62 F1 90"))
    assert not pattern.matches(bytes.fromhex("62 F1"))
    assert not pattern.matches(bytes.fromhex("62 F1 90 00"))


def test_payload_mask_can_match_selected_bits() -> None:
    pattern = PayloadPattern.parse("A0/F0 55")

    assert pattern.matches(bytes.fromhex("AF 55"))
    assert not pattern.matches(bytes.fromhex("9F 55"))


def test_payload_prefix_and_contains_modes() -> None:
    prefix = PayloadPattern.parse("7F 27", mode=PayloadMatchMode.PREFIX)
    contains = PayloadPattern.parse("27 35", mode=PayloadMatchMode.CONTAINS)
    payload = bytes.fromhex("7F 27 35 00")

    assert prefix.matches(payload)
    assert contains.matches(payload)


def test_compact_payload_pattern_is_supported() -> None:
    pattern = PayloadPattern.parse("62F1??")

    assert pattern.matches(bytes.fromhex("62 F1 90"))


def test_payload_pattern_rejects_partial_or_invalid_bytes() -> None:
    with pytest.raises(PatternParseError):
        PayloadPattern.parse("62F")
    with pytest.raises(PatternParseError):
        PayloadPattern.parse("GG")
