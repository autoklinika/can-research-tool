from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Iterable

from .message_models import DecodedMessage, ProtocolKind, TransportKind


@dataclass(frozen=True, slots=True)
class LogicalMessageStatistics:
    protocol: ProtocolKind
    transport: TransportKind
    name: str
    arbitration_id: int | None
    is_extended_id: bool
    pgn: int | None
    source_address: int | None
    destination_address: int | None
    message_count: int
    complete_count: int
    incomplete_count: int
    payload_lengths: tuple[int, ...]
    unique_payloads: int
    mean_period_ms: float | None
    min_period_ms: float | None
    max_period_ms: float | None
    estimated_frequency_hz: float | None
    changing_byte_mask: tuple[bool, ...]


class LogicalMessageAnalyzer:
    """Statistics calculated after transport reassembly."""

    def summarize(
        self,
        messages: Iterable[DecodedMessage],
    ) -> list[LogicalMessageStatistics]:
        grouped: dict[tuple[object, ...], list[DecodedMessage]] = defaultdict(list)
        for decoded in messages:
            message = decoded.message
            key = (
                decoded.protocol,
                message.transport,
                decoded.name,
                message.arbitration_id,
                message.is_extended_id,
                message.pgn,
                message.source_address,
                message.destination_address,
            )
            grouped[key].append(decoded)

        summaries = [self._summarize_group(group) for group in grouped.values()]
        return sorted(
            summaries,
            key=lambda item: (
                item.protocol.value,
                item.transport.value,
                -1 if item.pgn is None else item.pgn,
                -1 if item.arbitration_id is None else item.arbitration_id,
                item.name,
            ),
        )

    @staticmethod
    def _summarize_group(
        messages: list[DecodedMessage],
    ) -> LogicalMessageStatistics:
        ordered = sorted(
            messages,
            key=lambda item: (
                item.message.first_timestamp_ns,
                item.message.sequence,
            ),
        )
        periods_ms = [
            (
                current.message.first_timestamp_ns
                - previous.message.first_timestamp_ns
            )
            / 1_000_000
            for previous, current in zip(ordered, ordered[1:])
            if current.message.first_timestamp_ns
            >= previous.message.first_timestamp_ns
        ]
        mean_period_ms = mean(periods_ms) if periods_ms else None
        frequency_hz = (
            1000.0 / mean_period_ms
            if mean_period_ms is not None and mean_period_ms > 0
            else None
        )

        maximum_length = max(
            (len(item.message.payload) for item in ordered),
            default=0,
        )
        changing_mask = tuple(
            len(
                {
                    item.message.payload[index]
                    for item in ordered
                    if index < len(item.message.payload)
                }
            )
            > 1
            for index in range(maximum_length)
        )

        first = ordered[0]
        first_message = first.message
        complete_count = sum(item.message.complete for item in ordered)
        return LogicalMessageStatistics(
            protocol=first.protocol,
            transport=first_message.transport,
            name=first.name,
            arbitration_id=first_message.arbitration_id,
            is_extended_id=first_message.is_extended_id,
            pgn=first_message.pgn,
            source_address=first_message.source_address,
            destination_address=first_message.destination_address,
            message_count=len(ordered),
            complete_count=complete_count,
            incomplete_count=len(ordered) - complete_count,
            payload_lengths=tuple(
                sorted({len(item.message.payload) for item in ordered})
            ),
            unique_payloads=len(
                {item.message.payload for item in ordered}
            ),
            mean_period_ms=mean_period_ms,
            min_period_ms=min(periods_ms) if periods_ms else None,
            max_period_ms=max(periods_ms) if periods_ms else None,
            estimated_frequency_hz=frequency_hz,
            changing_byte_mask=changing_mask,
        )
