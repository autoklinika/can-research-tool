from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol

from .custom_rules import MessageRule, RuleBasedDecoder
from .dbc import DbcDecoder
from .j1939 import decode_j1939_identifier
from .message_models import DecodedMessage, ProtocolKind, TransportKind, TransportMessage
from .protocol_catalog import (
    UDS_DID_SERVICES,
    UDS_SERVICE_NAMES,
    UDS_SUBFUNCTION_SERVICES,
    j1939_pgn_name,
    uds_nrc_name,
    uds_service_name,
)


class ProtocolDecoder(Protocol):
    def matches(self, message: TransportMessage) -> bool: ...

    def decode(self, message: TransportMessage) -> DecodedMessage: ...


class UdsDecoder:
    """Decode the UDS application envelope after ISO-TP reassembly.

    The decoder intentionally stops at fields that can be interpreted without an
    ECU-specific database. Raw payload and transport metadata always remain
    available for later research rules.
    """

    def matches(self, message: TransportMessage) -> bool:
        if message.transport is not TransportKind.ISOTP or not message.payload:
            return False
        sid = message.payload[0]
        return sid == 0x7F or sid in UDS_SERVICE_NAMES or sid - 0x40 in UDS_SERVICE_NAMES

    def decode(self, message: TransportMessage) -> DecodedMessage:
        payload = message.payload
        sid = payload[0]
        fields: dict[str, object] = {
            "service_id": sid,
            "complete": message.complete,
            "payload_length": len(payload),
            "frame_count": message.frame_count,
            "source_address": message.source_address,
            "destination_address": message.destination_address,
        }
        fields.update(message.metadata)

        if sid == 0x7F:
            requested_sid = payload[1] if len(payload) >= 2 else None
            nrc = payload[2] if len(payload) >= 3 else None
            service_name = uds_service_name(requested_sid)
            nrc_name = uds_nrc_name(nrc)
            fields.update(
                {
                    "direction": "negative-response",
                    "response_type": "negative-response",
                    "requested_service_id": requested_sid,
                    "requested_service_name": service_name,
                    "negative_response_code": nrc,
                    "negative_response_name": nrc_name,
                }
            )
            nrc_text = "??" if nrc is None else f"{nrc:02X}"
            return DecodedMessage(
                message=message,
                protocol=ProtocolKind.UDS,
                name=f"UDS NEG {service_name} — NRC 0x{nrc_text} {nrc_name}",
                fields=fields,
                confidence=1.0,
            )

        base_sid, response_type = self._base_service(sid)
        direction = "positive-response" if response_type == "positive-response" else "request"
        service_name = uds_service_name(base_sid)
        fields.update(
            {
                "direction": direction,
                "response_type": response_type,
                "base_service_id": base_sid,
                "service_name": service_name,
            }
        )

        subfunction: int | None = None
        if base_sid in UDS_SUBFUNCTION_SERVICES and len(payload) >= 2:
            subfunction = payload[1] & 0x7F
            fields["subfunction_raw"] = payload[1]
            fields["subfunction"] = subfunction
            fields["suppress_positive_response"] = bool(payload[1] & 0x80)

        did: int | None = None
        if base_sid in UDS_DID_SERVICES and len(payload) >= 3:
            did = int.from_bytes(payload[1:3], "big")
            fields["did"] = did
            fields["did_hex"] = f"0x{did:04X}"

        routine_id: int | None = None
        if base_sid == 0x31 and len(payload) >= 4:
            routine_id = int.from_bytes(payload[2:4], "big")
            fields["routine_id"] = routine_id
            fields["routine_id_hex"] = f"0x{routine_id:04X}"

        if base_sid == 0x27 and subfunction is not None:
            fields["security_access_type"] = (
                "request-seed" if subfunction % 2 == 1 else "send-key"
            )
            fields["security_level"] = (subfunction + 1) // 2

        if base_sid == 0x36 and len(payload) >= 2:
            fields["block_sequence_counter"] = payload[1]

        if base_sid in (0x34, 0x35) and len(payload) >= 3:
            fields["data_format_identifier"] = payload[1]
            fields["address_and_length_format_identifier"] = payload[2]

        if base_sid == 0x19 and subfunction is not None:
            fields["dtc_subfunction"] = subfunction

        prefix = "POS" if response_type == "positive-response" else "REQ"
        suffix = self._summary_suffix(
            did=did,
            routine_id=routine_id,
            subfunction=subfunction,
            base_sid=base_sid,
        )
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.UDS,
            name=f"UDS {prefix} 0x{sid:02X} {service_name}{suffix}",
            fields=fields,
            confidence=1.0,
        )

    @staticmethod
    def _base_service(sid: int) -> tuple[int, str]:
        candidate = sid - 0x40
        if 0 <= candidate <= 0xFF and candidate in UDS_SERVICE_NAMES:
            return candidate, "positive-response"
        return sid, "request"

    @staticmethod
    def _summary_suffix(
        *,
        did: int | None,
        routine_id: int | None,
        subfunction: int | None,
        base_sid: int,
    ) -> str:
        if did is not None:
            return f" DID 0x{did:04X}"
        if routine_id is not None:
            return f" RID 0x{routine_id:04X}"
        if base_sid == 0x27 and subfunction is not None:
            access_type = "seed" if subfunction % 2 == 1 else "key"
            return f" level {(subfunction + 1) // 2} {access_type}"
        if subfunction is not None:
            return f" sub 0x{subfunction:02X}"
        return ""


class J1939TransportDecoder:
    """Interpret a reconstructed J1939 TP application payload."""

    def matches(self, message: TransportMessage) -> bool:
        return message.transport in (
            TransportKind.J1939_BAM,
            TransportKind.J1939_RTS_CTS,
        )

    def decode(self, message: TransportMessage) -> DecodedMessage:
        pgn_name = j1939_pgn_name(message.pgn)
        fields: dict[str, object] = {
            "pgn": message.pgn,
            "pgn_hex": None if message.pgn is None else f"0x{message.pgn:05X}",
            "pgn_name": pgn_name,
            "source_address": message.source_address,
            "destination_address": message.destination_address,
            "direction": "broadcast" if message.destination_address in (None, 0xFF) else "peer-to-peer",
            "complete": message.complete,
            "transport": message.transport.value,
            "payload_length": len(message.payload),
            "frame_count": message.frame_count,
        }
        fields.update(message.metadata)
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.J1939,
            name=f"J1939 {pgn_name}",
            fields=fields,
            confidence=1.0,
        )


class J1939SingleFrameDecoder:
    """Classify a raw 29-bit frame using the J1939 identifier layout.

    This is deliberately placed after DBC and user rules. A project-specific
    decoder therefore wins over the generic J1939 interpretation.
    """

    def matches(self, message: TransportMessage) -> bool:
        return (
            message.transport is TransportKind.RAW
            and message.is_extended_id
            and message.arbitration_id is not None
        )

    def decode(self, message: TransportMessage) -> DecodedMessage:
        assert message.arbitration_id is not None
        identifier = decode_j1939_identifier(message.arbitration_id)
        pgn_name = j1939_pgn_name(identifier.pgn)
        broadcast = identifier.destination_address in (None, 0xFF)
        fields: dict[str, object] = {
            "classification_basis": "29-bit J1939 identifier layout",
            "priority": identifier.priority,
            "extended_data_page": identifier.extended_data_page,
            "data_page": identifier.data_page,
            "pdu_format": identifier.pdu_format,
            "pdu_specific": identifier.pdu_specific,
            "pdu_type": "PDU1" if identifier.is_pdu1 else "PDU2",
            "pgn": identifier.pgn,
            "pgn_hex": f"0x{identifier.pgn:05X}",
            "pgn_name": pgn_name,
            "source_address": identifier.source_address,
            "destination_address": identifier.destination_address,
            "direction": "broadcast" if broadcast else "peer-to-peer",
            "payload_length": len(message.payload),
            "complete": message.complete,
        }
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.J1939,
            name=f"J1939 {pgn_name}",
            fields=fields,
            confidence=0.85,
        )


class UnknownDecoder:
    """Fallback that preserves proprietary traffic without inventing semantics."""

    def matches(self, message: TransportMessage) -> bool:
        return True

    def decode(self, message: TransportMessage) -> DecodedMessage:
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.UNKNOWN,
            name="Unknown / proprietary CAN message",
            fields={
                "complete": message.complete,
                "payload_length": len(message.payload),
                "frame_count": message.frame_count,
            },
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
        self._decoders.extend((J1939SingleFrameDecoder(), UnknownDecoder()))

    def decode(self, message: TransportMessage) -> DecodedMessage:
        for decoder in self._decoders:
            if decoder.matches(message):
                return decoder.decode(message)
        raise RuntimeError("protocol registry has no matching decoder")

    def decode_all(self, messages: Iterable[TransportMessage]) -> list[DecodedMessage]:
        return [self.decode(message) for message in messages]
