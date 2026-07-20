from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .message_models import DecodedMessage, ProtocolKind, TransportKind, TransportMessage


@dataclass(frozen=True, slots=True)
class MessageRule:
    """User-defined label for proprietary traffic."""

    name: str
    arbitration_id: int
    arbitration_mask: int = 0x1FFFFFFF
    is_extended_id: bool | None = None
    transport: TransportKind | None = None
    minimum_payload_length: int | None = None
    maximum_payload_length: int | None = None

    def matches(self, message: TransportMessage) -> bool:
        if message.arbitration_id is None:
            return False
        if self.is_extended_id is not None and message.is_extended_id != self.is_extended_id:
            return False
        if self.transport is not None and message.transport is not self.transport:
            return False
        if (
            message.arbitration_id & self.arbitration_mask
            != self.arbitration_id & self.arbitration_mask
        ):
            return False
        payload_length = len(message.payload)
        if (
            self.minimum_payload_length is not None
            and payload_length < self.minimum_payload_length
        ):
            return False
        if (
            self.maximum_payload_length is not None
            and payload_length > self.maximum_payload_length
        ):
            return False
        return True


class RuleBasedDecoder:
    """Protocol plugin that marks traffic selected by user-defined rules."""

    def __init__(self, rules: Iterable[MessageRule]) -> None:
        self._rules = tuple(rules)

    def matches(self, message: TransportMessage) -> bool:
        return any(rule.matches(message) for rule in self._rules)

    def decode(self, message: TransportMessage) -> DecodedMessage:
        rule = next(rule for rule in self._rules if rule.matches(message))
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.PROPRIETARY,
            name=rule.name,
            fields={
                "rule_name": rule.name,
                "arbitration_mask": rule.arbitration_mask,
                "complete": message.complete,
            },
            confidence=1.0,
        )
