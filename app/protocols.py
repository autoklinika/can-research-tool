from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol

from .custom_rules import MessageRule, RuleBasedDecoder
from .dbc import DbcDecoder
from .j1939 import decode_j1939_identifier
from .message_models import DecodedMessage, ProtocolKind, TransportKind, TransportMessage


class ProtocolDecoder(Protocol):
    def matches(self, message: TransportMessage) -> bool: ...

    def decode(self, message: TransportMessage) -> DecodedMessage: ...


_UDS_SERVICES: dict[int, str] = {
    0x10: "DiagnosticSessionControl",
    0x11: "ECUReset",
    0x14: "ClearDiagnosticInformation",
    0x19: "ReadDTCInformation",
    0x22: "ReadDataByIdentifier",
    0x23: "ReadMemoryByAddress",
    0x24: "ReadScalingDataByIdentifier",
    0x27: "SecurityAccess",
    0x28: "CommunicationControl",
    0x29: "Authentication",
    0x2A: "ReadDataByPeriodicIdentifier",
    0x2C: "DynamicallyDefineDataIdentifier",
    0x2E: "WriteDataByIdentifier",
    0x2F: "InputOutputControlByIdentifier",
    0x31: "RoutineControl",
    0x34: "RequestDownload",
    0x35: "RequestUpload",
    0x36: "TransferData",
    0x37: "RequestTransferExit",
    0x3D: "WriteMemoryByAddress",
    0x3E: "TesterPresent",
    0x83: "AccessTimingParameter",
    0x84: "SecuredDataTransmission",
    0x85: "ControlDTCSetting",
    0x86: "ResponseOnEvent",
    0x87: "LinkControl",
}

_UDS_SUBFUNCTION_SERVICES = {
    0x10,
    0x11,
    0x19,
    0x27,
    0x28,
    0x31,
    0x3E,
    0x83,
    0x85,
    0x86,
    0x87,
}

_UDS_DID_SERVICES = {0x22, 0x2E, 0x2F}


class UdsDecoder:
    """Decode a conservative UDS service envelope after ISO-TP reassembly."""

    def matches(self, message: TransportMessage) -> bool:
        if message.transport is not TransportKind.ISOTP or not message.payload:
            return False
        sid = message.payload[0]
        return sid == 0x7F or sid in _UDS_SERVICES or sid - 0x40 in _UDS_SERVICES

    def decode(self, message: TransportMessage) -> DecodedMessage:
        payload = message.payload
        sid = payload[0]
        fields: dict[str, object] = {
            "service_id": sid,
            "complete": message.complete,
        }

        if sid == 0x7F:
            requested_sid = payload[1] if len(payload) >= 2 else None
            nrc = payload[2] if len(payload) >= 3 else None
            service_name = (
                _UDS_SERVICES.get(requested_sid, f"Service0x{requested_sid:02X}")
                if requested_sid is not None
                else "UnknownService"
            )
            fields.update(
                {
                    "response_type": "negative-response",
                    "requested_service_id": requested_sid,
                    "requested_service_name": service_name,
                    "negative_response_code": nrc,
                }
            )
            return DecodedMessage(
                message=message,
                protocol=ProtocolKind.UDS,
                name=f"UDS negative response to {service_name}",
                fields=fields,
                confidence=1.0,
            )

        base_sid, response_type = self._base_service(sid)
        service_name = _UDS_SERVICES.get(base_sid, f"Service0x{base_sid:02X}")
        fields.update(
            {
                "base_service_id": base_sid,
                "service_name": service_name,
                "response_type": response_type,
            }
        )

        if base_sid in _UDS_SUBFUNCTION_SERVICES and len(payload) >= 2:
            fields["subfunction"] = payload[1] & 0x7F
            fields["suppress_positive_response"] = bool(payload[1] & 0x80)

        if base_sid in _UDS_DID_SERVICES and len(payload) >= 3:
            fields["did"] = int.from_bytes(payload[1:3], "big")

        if base_sid == 0x31 and len(payload) >= 4:
            fields["routine_id"] = int.from_bytes(payload[2:4], "big")

        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.UDS,
            name=f"UDS 0x{sid:02X} {service_name} ({response_type})",
            fields=fields,
            confidence=1.0,
        )

    @staticmethod
    def _base_service(sid: int) -> tuple[int, str]:
        candidate = sid - 0x40
        if 0 <= candidate <= 0xFF and candidate in _UDS_SERVICES:
            return candidate, "positive-response"
        return sid, "request"


class J1939TransportDecoder:
    def matches(self, message: TransportMessage) -> bool:
        return message.transport in (
            TransportKind.J1939_BAM,
            TransportKind.J1939_RTS_CTS,
        )

    def decode(self, message: TransportMessage) -> DecodedMessage:
        pgn = message.pgn
        pgn_text = "unknown" if pgn is None else f"0x{pgn:05X}"
        fields: dict[str, object] = {
            "pgn": pgn,
            "source_address": message.source_address,
            "destination_address": message.destination_address,
            "complete": message.complete,
            "transport": message.transport.value,
        }
        fields.update(message.metadata)
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.J1939,
            name=f"J1939 PGN {pgn_text}",
            fields=fields,
            confidence=1.0,
        )


class UnknownDecoder:
    """Fallback that preserves proprietary traffic without inventing semantics."""

    def matches(self, message: TransportMessage) -> bool:
        return True

    def decode(self, message: TransportMessage) -> DecodedMessage:
        fields: dict[str, object] = {"complete": message.complete}
        if message.is_extended_id and message.arbitration_id is not None:
            identifier = decode_j1939_identifier(message.arbitration_id)
            fields["j1939_identifier_candidate"] = {
                "priority": identifier.priority,
                "pgn": identifier.pgn,
                "source_address": identifier.source_address,
                "destination_address": identifier.destination_address,
            }

        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.UNKNOWN,
            name="Unknown / proprietary CAN message",
            fields=fields,
            confidence=0.0,
        )


class ProtocolRegistry:
    """Ordered protocol-decoder registry with an explicit unknown fallback."""

    def __init__(
        self,
        decoders: Iterable[ProtocolDecoder] | None = None,
        *,
        custom_rules: Iterable[MessageRule] = (),
        dbc_paths: Iterable[str | Path] = (),
    ) -> None:
        if decoders is not None:
            self._decoders = list(decoders)
            return

        rules = tuple(custom_rules)
        active_dbc_paths = tuple(Path(path) for path in dbc_paths)
        self._decoders: list[ProtocolDecoder] = [
            UdsDecoder(),
            J1939TransportDecoder(),
        ]
        if active_dbc_paths:
            self._decoders.append(DbcDecoder(active_dbc_paths))
        if rules:
            self._decoders.append(RuleBasedDecoder(rules))
        self._decoders.append(UnknownDecoder())

    def decode(self, message: TransportMessage) -> DecodedMessage:
        for decoder in self._decoders:
            if decoder.matches(message):
                return decoder.decode(message)
        raise RuntimeError("protocol registry has no matching decoder")

    def decode_all(self, messages: Iterable[TransportMessage]) -> list[DecodedMessage]:
        return [self.decode(message) for message in messages]
