from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .filters import FilterMode, FilterPreset


class IsoTpAddressing(StrEnum):
    """Addressing layouts currently detected by CRT's ISO-TP reassembler."""

    NORMAL_11BIT = "normal-11bit"
    NORMAL_FIXED_29BIT = "normal-fixed-29bit"


class IsoTpFraming(StrEnum):
    """Logical-message framing derived from the number of contributing CAN frames."""

    SINGLE_FRAME = "single-frame"
    MULTI_FRAME = "multi-frame"


class IsoTpCompletion(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class IsoTpFilterSpec:
    """Build an ISO-TP preset for the shared global filter compiler.

    The specification deliberately uses only facts retained by ``LogicalMessageRecord``:
    transport kind, CAN identifier width, addresses, source-frame count, lengths,
    completion and error text. Flow Control parameters such as block size and STmin are
    not available after the current reassembly pipeline and are therefore not invented.

    ``SINGLE_FRAME`` means that the logical message was built from one source CAN frame.
    A malformed or orphan ISO-TP frame can also have one source frame; combine it with
    ``has_error=False`` or ``completion=COMPLETE`` when only valid Single Frames are
    desired.
    """

    addressing: IsoTpAddressing | None = None
    framing: IsoTpFraming | None = None
    completion: IsoTpCompletion | None = None
    has_error: bool | None = None
    can_ids: tuple[int, ...] = ()
    source_addresses: tuple[int, ...] = ()
    destination_addresses: tuple[int, ...] = ()
    min_declared_payload_length: int | None = None
    max_declared_payload_length: int | None = None
    min_received_payload_length: int | None = None
    max_received_payload_length: int | None = None
    min_source_frame_count: int | None = None
    max_source_frame_count: int | None = None

    def to_preset(
        self,
        name: str,
        *,
        mode: FilterMode = FilterMode.INCLUDE,
        enabled: bool = True,
        scope: Iterable[str] = ("live", "stored_session"),
    ) -> FilterPreset:
        self._validate()

        children: list[dict[str, object]] = [_condition("transport", "isotp")]

        if self.addressing is IsoTpAddressing.NORMAL_11BIT:
            children.append(_condition("frame_format", "std"))
        elif self.addressing is IsoTpAddressing.NORMAL_FIXED_29BIT:
            children.append(_condition("frame_format", "ext"))

        if self.framing is IsoTpFraming.SINGLE_FRAME:
            children.append(_condition("source_frame_count", 1))
        elif self.framing is IsoTpFraming.MULTI_FRAME:
            children.append(_condition("source_frame_count", 1, operator="gt"))

        if self.completion is IsoTpCompletion.COMPLETE:
            children.append(_condition("complete", True))
        elif self.completion is IsoTpCompletion.INCOMPLETE:
            children.append(_condition("complete", False))

        if self.has_error is True:
            children.append(_condition("error", "", operator="ne"))
        elif self.has_error is False:
            children.append(_condition("error", ""))

        _append_membership(children, "can_id", self.can_ids)
        _append_membership(children, "source_address", self.source_addresses)
        _append_membership(children, "destination_address", self.destination_addresses)

        _append_range(
            children,
            "declared_payload_length",
            self.min_declared_payload_length,
            self.max_declared_payload_length,
        )
        _append_range(
            children,
            "received_payload_length",
            self.min_received_payload_length,
            self.max_received_payload_length,
        )
        _append_range(
            children,
            "source_frame_count",
            self.min_source_frame_count,
            self.max_source_frame_count,
        )

        preset = FilterPreset.create(name)
        preset.mode = mode
        preset.enabled = enabled
        preset.scope = [str(item) for item in scope]
        preset.root = {
            "type": "group",
            "operator": "and",
            "children": children,
        }
        return preset

    def _validate(self) -> None:
        _validate_values("CAN ID", self.can_ids, 0, 0x1FFFFFFF)
        _validate_values("Source Address", self.source_addresses, 0, 0xFF)
        _validate_values("Destination Address", self.destination_addresses, 0, 0xFF)
        _validate_range(
            "deklarowana długość payloadu",
            self.min_declared_payload_length,
            self.max_declared_payload_length,
        )
        _validate_range(
            "odebrana długość payloadu",
            self.min_received_payload_length,
            self.max_received_payload_length,
        )
        _validate_range(
            "liczba ramek źródłowych",
            self.min_source_frame_count,
            self.max_source_frame_count,
            minimum_allowed=1,
        )


def _condition(field: str, value: object, *, operator: str = "eq") -> dict[str, object]:
    return {
        "type": "condition",
        "field": field,
        "operator": operator,
        "values": [value],
    }


def _append_membership(
    children: list[dict[str, object]],
    field: str,
    values: tuple[int, ...],
) -> None:
    if not values:
        return
    children.append(
        {
            "type": "condition",
            "field": field,
            "operator": "in",
            "values": list(values),
        }
    )


def _append_range(
    children: list[dict[str, object]],
    field: str,
    minimum: int | None,
    maximum: int | None,
) -> None:
    if minimum is None and maximum is None:
        return
    if minimum is not None and maximum is not None:
        if minimum == maximum:
            children.append(_condition(field, minimum))
        else:
            children.append(
                {
                    "type": "condition",
                    "field": field,
                    "operator": "between",
                    "values": [minimum, maximum],
                }
            )
        return
    if minimum is not None:
        children.append(_condition(field, minimum, operator="ge"))
        return
    children.append(_condition(field, maximum, operator="le"))


def _validate_values(name: str, values: tuple[int, ...], minimum: int, maximum: int) -> None:
    if any(not minimum <= int(value) <= maximum for value in values):
        raise ValueError(f"{name} musi należeć do zakresu {minimum}–{maximum}.")


def _validate_range(
    name: str,
    minimum: int | None,
    maximum: int | None,
    *,
    minimum_allowed: int = 0,
) -> None:
    if minimum is not None and minimum < minimum_allowed:
        raise ValueError(f"{name}: minimum nie może być mniejsze niż {minimum_allowed}.")
    if maximum is not None and maximum < minimum_allowed:
        raise ValueError(f"{name}: maksimum nie może być mniejsze niż {minimum_allowed}.")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError(f"{name}: minimum nie może być większe niż maksimum.")
