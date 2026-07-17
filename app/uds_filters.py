from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Iterable

from .filters import FilterMode, FilterPreset
from .protocol_catalog import UDS_DID_SERVICES, UDS_SUBFUNCTION_SERVICES


class UdsService(IntEnum):
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECU_RESET = 0x11
    CLEAR_DIAGNOSTIC_INFORMATION = 0x14
    READ_DTC_INFORMATION = 0x19
    READ_DATA_BY_IDENTIFIER = 0x22
    READ_MEMORY_BY_ADDRESS = 0x23
    READ_SCALING_DATA_BY_IDENTIFIER = 0x24
    SECURITY_ACCESS = 0x27
    COMMUNICATION_CONTROL = 0x28
    AUTHENTICATION = 0x29
    READ_DATA_BY_PERIODIC_IDENTIFIER = 0x2A
    DYNAMICALLY_DEFINE_DATA_IDENTIFIER = 0x2C
    WRITE_DATA_BY_IDENTIFIER = 0x2E
    INPUT_OUTPUT_CONTROL_BY_IDENTIFIER = 0x2F
    ROUTINE_CONTROL = 0x31
    REQUEST_DOWNLOAD = 0x34
    REQUEST_UPLOAD = 0x35
    TRANSFER_DATA = 0x36
    REQUEST_TRANSFER_EXIT = 0x37
    REQUEST_FILE_TRANSFER = 0x38
    WRITE_MEMORY_BY_ADDRESS = 0x3D
    TESTER_PRESENT = 0x3E
    ACCESS_TIMING_PARAMETER = 0x83
    SECURED_DATA_TRANSMISSION = 0x84
    CONTROL_DTC_SETTING = 0x85
    RESPONSE_ON_EVENT = 0x86
    LINK_CONTROL = 0x87


class UdsDirection(StrEnum):
    REQUEST = "request"
    POSITIVE_RESPONSE = "positive-response"
    NEGATIVE_RESPONSE = "negative-response"


class UdsSecurityAccessPhase(StrEnum):
    REQUEST_SEED = "request-seed"
    SEND_KEY = "send-key"


@dataclass(frozen=True, slots=True)
class UdsFilterSpec:
    """Build a UDS preset for the shared global filter compiler.

    The profile compiles domain-level selections into the existing filter tree:
    protocol, ISO-TP transport, base/raw SID, direction, NRC, DID, Routine ID,
    subfunction, payload length and addressing. SecurityAccess phase and level are
    reduced to the standard UDS subfunction values, so no second evaluator is needed.

    The decoder retains ``suppress_positive_response`` in ``LogicalMessageRecord.fields``,
    but the shared ``FilterContext`` does not expose that boolean yet. This profile does
    not infer the flag from the masked subfunction; doing so would create false matches.
    """

    services: tuple[UdsService | int, ...] = ()
    sids: tuple[int, ...] = ()
    directions: tuple[UdsDirection | str, ...] = ()
    nrcs: tuple[int, ...] = ()
    dids: tuple[int, ...] = ()
    routine_ids: tuple[int, ...] = ()
    subfunctions: tuple[int, ...] = ()
    security_access_phase: UdsSecurityAccessPhase | None = None
    security_levels: tuple[int, ...] = ()
    can_ids: tuple[int, ...] = ()
    source_addresses: tuple[int, ...] = ()
    destination_addresses: tuple[int, ...] = ()
    min_payload_length: int | None = None
    max_payload_length: int | None = None
    complete: bool | None = None

    @classmethod
    def for_service(
        cls,
        service: UdsService | int,
        *,
        direction: UdsDirection | str | None = None,
        **kwargs: object,
    ) -> UdsFilterSpec:
        directions: tuple[UdsDirection | str, ...] = ()
        if direction is not None:
            directions = (direction,)
        return cls(services=(service,), directions=directions, **kwargs)

    @classmethod
    def negative_responses(
        cls,
        *,
        services: Iterable[UdsService | int] = (),
        nrcs: Iterable[int] = (),
        **kwargs: object,
    ) -> UdsFilterSpec:
        return cls(
            services=tuple(services),
            directions=(UdsDirection.NEGATIVE_RESPONSE,),
            nrcs=tuple(nrcs),
            **kwargs,
        )

    def to_preset(
        self,
        name: str,
        *,
        mode: FilterMode = FilterMode.INCLUDE,
        enabled: bool = True,
        scope: Iterable[str] = ("live", "stored_session"),
    ) -> FilterPreset:
        services, directions, subfunctions = self._normalized_constraints()

        children: list[dict[str, object]] = [
            _condition("protocol", "uds"),
            _condition("transport", "isotp"),
        ]

        _append_membership(children, "base_sid", services)
        _append_membership(children, "sid", self.sids)
        _append_membership(children, "direction", directions)
        _append_membership(children, "nrc", self.nrcs)
        _append_membership(children, "did", self.dids)
        _append_membership(children, "routine_id", self.routine_ids)
        _append_membership(children, "subfunction", subfunctions)
        _append_membership(children, "can_id", self.can_ids)
        _append_membership(children, "source_address", self.source_addresses)
        _append_membership(children, "destination_address", self.destination_addresses)
        _append_range(
            children,
            "payload_length",
            self.min_payload_length,
            self.max_payload_length,
        )

        if self.complete is not None:
            children.append(_condition("complete", self.complete))

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

    def _normalized_constraints(self) -> tuple[tuple[int, ...], tuple[str, ...], tuple[int, ...]]:
        services = _unique_ints(self.services)
        directions = tuple(dict.fromkeys(_normalize_direction(value) for value in self.directions))
        subfunctions = set(_unique_ints(self.subfunctions))

        self._validate_common(services, directions)

        if self.nrcs:
            if directions and UdsDirection.NEGATIVE_RESPONSE.value not in directions:
                raise ValueError("NRC można łączyć wyłącznie z kierunkiem negative-response.")
            if not directions:
                directions = (UdsDirection.NEGATIVE_RESPONSE.value,)

        has_security_filter = self.security_access_phase is not None or bool(self.security_levels)
        if has_security_filter:
            if services and int(UdsService.SECURITY_ACCESS) not in services:
                raise ValueError("Filtr poziomu/fazy SecurityAccess wymaga usługi 0x27.")
            if not services:
                services = (int(UdsService.SECURITY_ACCESS),)
            derived = _security_subfunctions(
                self.security_access_phase,
                self.security_levels,
            )
            subfunctions = derived if not subfunctions else subfunctions.intersection(derived)
            if not subfunctions:
                raise ValueError("Warunki SecurityAccess i subfunction nie mają części wspólnej.")

        if self.dids and services and not any(service in UDS_DID_SERVICES for service in services):
            raise ValueError("Filtr DID wymaga usługi UDS obsługującej DID.")
        if self.routine_ids and services and int(UdsService.ROUTINE_CONTROL) not in services:
            raise ValueError("Filtr Routine ID wymaga usługi RoutineControl 0x31.")
        if subfunctions and services and not any(
            service in UDS_SUBFUNCTION_SERVICES for service in services
        ):
            raise ValueError("Wybrane usługi UDS nie udostępniają subfunction.")

        return services, directions, tuple(sorted(subfunctions))

    def _validate_common(self, services: tuple[int, ...], directions: tuple[str, ...]) -> None:
        _validate_values("Bazowy SID", services, 0, 0xFF)
        _validate_values("SID", self.sids, 0, 0xFF)
        _validate_values("NRC", self.nrcs, 0, 0xFF)
        _validate_values("DID", self.dids, 0, 0xFFFF)
        _validate_values("Routine ID", self.routine_ids, 0, 0xFFFF)
        _validate_values("Subfunction", self.subfunctions, 0, 0x7F)
        _validate_values("SecurityAccess level", self.security_levels, 1, 63)
        _validate_values("CAN ID", self.can_ids, 0, 0x1FFFFFFF)
        _validate_values("Source Address", self.source_addresses, 0, 0xFF)
        _validate_values("Destination Address", self.destination_addresses, 0, 0xFF)
        _validate_range(
            "długość payloadu",
            self.min_payload_length,
            self.max_payload_length,
        )
        allowed = {item.value for item in UdsDirection}
        if any(direction not in allowed for direction in directions):
            raise ValueError("Nieznany kierunek UDS.")


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
    values: Iterable[object],
) -> None:
    normalized = list(values)
    if not normalized:
        return
    children.append(
        {
            "type": "condition",
            "field": field,
            "operator": "in",
            "values": normalized,
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


def _normalize_direction(value: UdsDirection | str) -> str:
    if isinstance(value, UdsDirection):
        return value.value
    normalized = str(value).strip().casefold().replace("_", "-")
    aliases = {
        "req": UdsDirection.REQUEST.value,
        "request": UdsDirection.REQUEST.value,
        "positive": UdsDirection.POSITIVE_RESPONSE.value,
        "positive-response": UdsDirection.POSITIVE_RESPONSE.value,
        "pos": UdsDirection.POSITIVE_RESPONSE.value,
        "negative": UdsDirection.NEGATIVE_RESPONSE.value,
        "negative-response": UdsDirection.NEGATIVE_RESPONSE.value,
        "neg": UdsDirection.NEGATIVE_RESPONSE.value,
    }
    return aliases.get(normalized, normalized)


def _unique_ints(values: Iterable[IntEnum | int]) -> tuple[int, ...]:
    return tuple(dict.fromkeys(int(value) for value in values))


def _security_subfunctions(
    phase: UdsSecurityAccessPhase | None,
    levels: tuple[int, ...],
) -> set[int]:
    active_levels = levels or tuple(range(1, 64))
    values: set[int] = set()
    for level in active_levels:
        request_seed = 2 * int(level) - 1
        send_key = 2 * int(level)
        if phase in {None, UdsSecurityAccessPhase.REQUEST_SEED}:
            values.add(request_seed)
        if phase in {None, UdsSecurityAccessPhase.SEND_KEY}:
            values.add(send_key)
    return values


def _validate_values(name: str, values: Iterable[int], minimum: int, maximum: int) -> None:
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
