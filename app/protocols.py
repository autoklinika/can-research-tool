from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol

from .custom_rules import MessageRule, RuleBasedDecoder
from .dbc import DbcDecoder
from .j1939 import decode_j1939_identifier
from .message_models import DecodedMessage, ProtocolKind, TransportKind, TransportMessage
from .protocol_catalog import j1939_pgn_name
from .uds import UdsDecoder


class ProtocolDecoder(Protocol):
    def matches(self, message: TransportMessage) -> bool: ...

    def decode(self, message: TransportMessage) -> DecodedMessage: ...


class J1939TransportDecoder:
    """Interpret a reconstructed J1939 TP application payload."""

    def matches(self, message: TransportMessage) -> bool:
        return message.transport in (
            TransportKind.J1939_BAM,
            TransportKind.J1939_RTS_CTS,
        )

    def decode(self, message: TransportMessage) -> DecodedMessage:
        pgn_name = j1939_pgn_name(message.pgn)
        fields: dict[str, object] = dict(message.metadata)
        fields.update(
            {
                "pgn": message.pgn,
                "pgn_hex": None if message.pgn is None else f"0x{message.pgn:05X}",
                "pgn_name": pgn_name,
                "source_address": message.source_address,
                "destination_address": message.destination_address,
                "direction": (
                    "broadcast"
                    if message.destination_address in (None, 0xFF)
                    else "peer-to-peer"
                ),
                "complete": message.complete,
                "transport": message.transport.value,
                "payload_length": len(message.payload),
                "frame_count": message.frame_count,
            }
        )
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.J1939,
            name=f"J1939 {pgn_name}",
            fields=fields,
            confidence=1.0,
        )


class CanOpenDecoder:
    """Conservative CANopen classifier for standard 11-bit communication objects."""

    def matches(self, message: TransportMessage) -> bool:
        if (
            message.transport is not TransportKind.RAW
            or message.is_extended_id
            or message.arbitration_id is None
        ):
            return False
        can_id = int(message.arbitration_id)
        length = len(message.payload)
        if can_id == 0x000:
            return length == 2
        if can_id == 0x080:
            return length == 0
        if can_id == 0x100:
            return length == 6
        if 0x081 <= can_id <= 0x0FF:
            return length == 8
        if 0x180 <= can_id <= 0x57F:
            return length <= 8
        if 0x580 <= can_id <= 0x67F:
            return length == 8
        if 0x700 <= can_id <= 0x77F:
            return length == 1
        return False

    def decode(self, message: TransportMessage) -> DecodedMessage:
        assert message.arbitration_id is not None
        can_id = int(message.arbitration_id)
        function, node_id = self._object(can_id)
        fields: dict[str, object] = dict(message.metadata)
        fields.update(
            {
                "canopen_function": function,
                "node_id": node_id,
                "cob_id": can_id,
                "payload_length": len(message.payload),
                "complete": message.complete,
            }
        )
        if function == "NMT" and len(message.payload) >= 2:
            fields["nmt_command"] = message.payload[0]
            fields["target_node"] = message.payload[1]
        elif function == "Heartbeat" and message.payload:
            fields["nmt_state"] = message.payload[0]
        elif function.startswith("SDO") and message.payload:
            fields["command_specifier"] = message.payload[0]
            if len(message.payload) >= 4:
                fields["index"] = int.from_bytes(message.payload[1:3], "little")
                fields["index_hex"] = f"0x{fields['index']:04X}"
                fields["subindex"] = message.payload[3]
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.CANOPEN,
            name=f"CANopen {function}" + ("" if node_id is None else f" node 0x{node_id:02X}"),
            fields=fields,
            confidence=0.9,
        )

    @staticmethod
    def _object(can_id: int) -> tuple[str, int | None]:
        if can_id == 0x000:
            return "NMT", None
        if can_id == 0x080:
            return "SYNC", None
        if can_id == 0x100:
            return "TIME", None
        if 0x081 <= can_id <= 0x0FF:
            return "EMCY", can_id - 0x080
        ranges = (
            (0x180, "TPDO1"),
            (0x200, "RPDO1"),
            (0x280, "TPDO2"),
            (0x300, "RPDO2"),
            (0x380, "TPDO3"),
            (0x400, "RPDO3"),
            (0x480, "TPDO4"),
            (0x500, "RPDO4"),
            (0x580, "SDO response"),
            (0x600, "SDO request"),
            (0x700, "Heartbeat"),
        )
        for base, name in ranges:
            if base <= can_id <= base + 0x7F:
                return name, can_id - base
        return "Object", can_id & 0x7F


class J1939RawDecoder:
    """Optional classifier for explicitly confirmed single-frame J1939 traffic."""

    def matches(self, message: TransportMessage) -> bool:
        return bool(
            message.transport is TransportKind.RAW
            and message.is_extended_id
            and message.arbitration_id is not None
            and message.metadata.get("confirmed_j1939") is True
        )

    def decode(self, message: TransportMessage) -> DecodedMessage:
        assert message.arbitration_id is not None
        identifier = decode_j1939_identifier(message.arbitration_id)
        pgn_name = j1939_pgn_name(identifier.pgn)
        fields: dict[str, object] = dict(message.metadata)
        fields.update(
            {
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
                "payload_length": len(message.payload),
                "complete": message.complete,
            }
        )
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.J1939,
            name=f"J1939 {pgn_name}",
            fields=fields,
            confidence=1.0,
        )


class UnknownDecoder:
    """Fallback that preserves proprietary traffic without inventing semantics."""

    def matches(self, message: TransportMessage) -> bool:
        return True

    def decode(self, message: TransportMessage) -> DecodedMessage:
        fields: dict[str, object] = dict(message.metadata)
        fields.update(
            {
                "complete": message.complete,
                "payload_length": len(message.payload),
                "frame_count": message.frame_count,
            }
        )
        if message.is_extended_id and message.arbitration_id is not None:
            identifier = decode_j1939_identifier(message.arbitration_id)
            fields["j1939_identifier_candidate"] = {
                "classification_basis": "29-bit identifier layout only",
                "priority": identifier.priority,
                "extended_data_page": identifier.extended_data_page,
                "data_page": identifier.data_page,
                "pdu_format": identifier.pdu_format,
                "pdu_specific": identifier.pdu_specific,
                "pdu_type": "PDU1" if identifier.is_pdu1 else "PDU2",
                "pgn": identifier.pgn,
                "pgn_hex": f"0x{identifier.pgn:05X}",
                "pgn_name": j1939_pgn_name(identifier.pgn),
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
    """Ordered protocol-decoder registry with deterministic precedence."""

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
        self._decoders.extend(
            (
                CanOpenDecoder(),
                J1939RawDecoder(),
                UnknownDecoder(),
            )
        )

    def decode(self, message: TransportMessage) -> DecodedMessage:
        for decoder in self._decoders:
            if decoder.matches(message):
                return decoder.decode(message)
        raise RuntimeError("protocol registry has no matching decoder")

    def decode_all(self, messages: Iterable[TransportMessage]) -> list[DecodedMessage]:
        return [self.decode(message) for message in messages]
