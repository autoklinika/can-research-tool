from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

CAN_ID_MAX = 0x1FFFFFFF
MAX_RAW_PAYLOAD_BYTES = 64


class PatternParseError(ValueError):
    """Raised when a static filter pattern cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class CanIdPattern:
    """A canonical 29-bit CAN identifier value/mask pattern.

    Supported forms:

    - exact: ``0x18DAF900``
    - wildcard nibbles: ``0x18DA??F9``
    - explicit mask: ``0x18DA00F9/0x1FFF00FF``
    """

    value: int
    mask: int

    def __post_init__(self) -> None:
        if not 0 <= self.value <= CAN_ID_MAX:
            raise PatternParseError("CAN ID value must be in range 0x0-0x1FFFFFFF")
        if not 0 <= self.mask <= CAN_ID_MAX:
            raise PatternParseError("CAN ID mask must be in range 0x0-0x1FFFFFFF")
        if self.value & ~self.mask:
            raise PatternParseError("CAN ID value contains bits outside the mask")

    @classmethod
    def parse(cls, expression: str) -> CanIdPattern:
        text = expression.strip().lower().replace("_", "")
        if not text:
            raise PatternParseError("CAN ID pattern cannot be empty")

        if "/" in text:
            parts = text.split("/")
            if len(parts) != 2:
                raise PatternParseError("CAN ID mask form must be value/mask")
            value = _parse_int(parts[0], label="CAN ID value")
            mask = _parse_int(parts[1], label="CAN ID mask")
            _validate_can_id_component(value, "CAN ID value")
            _validate_can_id_component(mask, "CAN ID mask")
            return cls(value=value & mask, mask=mask)

        if "?" in text or "*" in text:
            digits = text[2:] if text.startswith("0x") else text
            if not 1 <= len(digits) <= 8:
                raise PatternParseError("wildcard CAN ID must contain 1-8 hexadecimal nibbles")

            value = 0
            mask = 0
            for character in digits:
                value <<= 4
                mask <<= 4
                if character in {"?", "*"}:
                    continue
                if character not in "0123456789abcdef":
                    raise PatternParseError(f"invalid CAN ID wildcard character: {character!r}")
                value |= int(character, 16)
                mask |= 0xF

            _validate_can_id_component(value, "CAN ID value")
            _validate_can_id_component(mask, "CAN ID mask")
            return cls(value=value, mask=mask)

        value = _parse_int(text, label="CAN ID")
        _validate_can_id_component(value, "CAN ID")
        return cls(value=value, mask=CAN_ID_MAX)

    def matches(self, can_id: int) -> bool:
        if not 0 <= int(can_id) <= CAN_ID_MAX:
            return False
        return (int(can_id) & self.mask) == self.value


class PayloadMatchMode(StrEnum):
    EXACT = "exact"
    PREFIX = "prefix"
    CONTAINS = "contains"


@dataclass(frozen=True, slots=True)
class PayloadPattern:
    """A byte-wise payload pattern with an independent bit mask per byte.

    Tokens may be:

    - exact bytes: ``62 F1 90``
    - wildcard bytes: ``62 ?? ??``
    - masked bytes: ``A0/F0`` (upper nibble must match)

    Compact exact/wildcard input such as ``62F1??`` is also accepted.
    """

    value: bytes
    mask: bytes
    mode: PayloadMatchMode = PayloadMatchMode.EXACT

    def __post_init__(self) -> None:
        if not self.value:
            raise PatternParseError("payload pattern cannot be empty")
        if len(self.value) != len(self.mask):
            raise PatternParseError("payload value and mask lengths differ")
        if len(self.value) > MAX_RAW_PAYLOAD_BYTES:
            raise PatternParseError(
                f"raw payload pattern cannot exceed {MAX_RAW_PAYLOAD_BYTES} bytes"
            )
        for value_byte, mask_byte in zip(self.value, self.mask, strict=True):
            if value_byte & ~mask_byte:
                raise PatternParseError("payload value contains bits outside its mask")

    @classmethod
    def parse(
        cls,
        expression: str,
        *,
        mode: PayloadMatchMode | str = PayloadMatchMode.EXACT,
    ) -> PayloadPattern:
        text = expression.strip()
        if not text:
            raise PatternParseError("payload pattern cannot be empty")

        try:
            normalized_mode = PayloadMatchMode(mode)
        except ValueError as exc:
            raise PatternParseError(f"unsupported payload match mode: {mode}") from exc

        tokens = _payload_tokens(text)
        values = bytearray()
        masks = bytearray()
        for token in tokens:
            value_byte, mask_byte = _parse_payload_token(token)
            values.append(value_byte)
            masks.append(mask_byte)

        return cls(value=bytes(values), mask=bytes(masks), mode=normalized_mode)

    def matches(self, payload: bytes | bytearray | memoryview) -> bool:
        actual = bytes(payload)
        pattern_length = len(self.value)

        if self.mode == PayloadMatchMode.EXACT:
            return len(actual) == pattern_length and self._matches_at(actual, 0)
        if self.mode == PayloadMatchMode.PREFIX:
            return len(actual) >= pattern_length and self._matches_at(actual, 0)
        if len(actual) < pattern_length:
            return False
        return any(
            self._matches_at(actual, offset)
            for offset in range(len(actual) - pattern_length + 1)
        )

    def _matches_at(self, payload: bytes, offset: int) -> bool:
        return all(
            (payload[offset + index] & mask_byte) == value_byte
            for index, (value_byte, mask_byte) in enumerate(
                zip(self.value, self.mask, strict=True)
            )
        )


def _parse_int(text: str, *, label: str) -> int:
    normalized = text.strip().lower()
    if not normalized:
        raise PatternParseError(f"{label} cannot be empty")
    try:
        return int(normalized, 16) if normalized.startswith("0x") else int(normalized, 10)
    except ValueError as exc:
        raise PatternParseError(f"invalid {label}: {text!r}") from exc


def _validate_can_id_component(value: int, label: str) -> None:
    if not 0 <= value <= CAN_ID_MAX:
        raise PatternParseError(f"{label} must be in range 0x0-0x1FFFFFFF")


def _payload_tokens(expression: str) -> list[str]:
    if re.search(r"[\s,;:-]", expression):
        tokens = [token for token in re.split(r"[\s,;:-]+", expression) if token]
    else:
        compact = expression[2:] if expression.lower().startswith("0x") else expression
        if "/" in compact:
            tokens = [compact]
        else:
            if len(compact) % 2:
                raise PatternParseError("compact payload pattern must contain full bytes")
            tokens = [compact[index : index + 2] for index in range(0, len(compact), 2)]

    if not tokens:
        raise PatternParseError("payload pattern cannot be empty")
    return tokens


def _parse_payload_token(token: str) -> tuple[int, int]:
    normalized = token.strip().lower()
    if normalized in {"??", "**"}:
        return 0, 0

    if "/" in normalized:
        parts = normalized.split("/")
        if len(parts) != 2:
            raise PatternParseError(f"masked payload byte must be value/mask: {token!r}")
        value = _parse_hex_byte(parts[0], label="payload value")
        mask = _parse_hex_byte(parts[1], label="payload mask")
        return value & mask, mask

    return _parse_hex_byte(normalized, label="payload byte"), 0xFF


def _parse_hex_byte(text: str, *, label: str) -> int:
    normalized = text[2:] if text.startswith("0x") else text
    if not re.fullmatch(r"[0-9a-f]{2}", normalized):
        raise PatternParseError(f"{label} must contain exactly two hexadecimal digits")
    return int(normalized, 16)
