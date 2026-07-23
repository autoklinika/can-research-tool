from __future__ import annotations

from typing import Any

from .message_models import DecodedMessage, ProtocolKind, TransportKind, TransportMessage
from .protocol_catalog import (
    UDS_SERVICE_NAMES,
    UDS_SUBFUNCTION_SERVICES,
    uds_nrc_name,
    uds_service_name,
)


class UdsDecoder:
    """Decode UDS application data after ISO-TP reassembly.

    The decoder is intentionally ECU-agnostic. It interprets standardized service
    envelopes and preserves all manufacturer-specific records as hexadecimal data.
    Variable-length DID values are not guessed; the first DID and its remaining data
    record are exposed until a DID-specific definition is available.
    """

    def matches(self, message: TransportMessage) -> bool:
        if message.transport is not TransportKind.ISOTP or not message.payload:
            return False
        sid = message.payload[0]
        return sid == 0x7F or sid in UDS_SERVICE_NAMES or sid - 0x40 in UDS_SERVICE_NAMES

    def decode(self, message: TransportMessage) -> DecodedMessage:
        payload = bytes(message.payload)
        sid = payload[0]
        fields: dict[str, Any] = dict(message.metadata)
        fields.update(
            {
                "service_id": sid,
                "service_id_hex": f"0x{sid:02X}",
                "application_payload_hex": _hex(payload),
                "complete": message.complete,
                "payload_length": len(payload),
                "frame_count": message.frame_count,
                "source_address": message.source_address,
                "destination_address": message.destination_address,
            }
        )

        if sid == 0x7F:
            return self._decode_negative_response(message, payload, fields)

        base_sid, response_type = self._base_service(sid)
        direction = "positive-response" if response_type == "positive-response" else "request"
        service_name = uds_service_name(base_sid)
        fields.update(
            {
                "direction": direction,
                "response_type": response_type,
                "base_service_id": base_sid,
                "base_service_id_hex": f"0x{base_sid:02X}",
                "service_name": service_name,
            }
        )

        subfunction = self._decode_common_subfunction(payload, base_sid, response_type, fields)
        self._decode_service_data(payload, base_sid, response_type, subfunction, fields)

        prefix = "POS" if response_type == "positive-response" else "REQ"
        suffix = self._summary_suffix(fields)
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.UDS,
            name=f"UDS {prefix} 0x{sid:02X} {service_name}{suffix}",
            fields=fields,
            confidence=1.0,
        )

    @staticmethod
    def _decode_negative_response(
        message: TransportMessage,
        payload: bytes,
        fields: dict[str, Any],
    ) -> DecodedMessage:
        requested_sid = payload[1] if len(payload) >= 2 else None
        nrc = payload[2] if len(payload) >= 3 else None
        service_name = uds_service_name(requested_sid)
        nrc_name = uds_nrc_name(nrc)
        fields.update(
            {
                "direction": "negative-response",
                "response_type": "negative-response",
                "requested_service_id": requested_sid,
                "requested_service_id_hex": (
                    None if requested_sid is None else f"0x{requested_sid:02X}"
                ),
                "requested_service_name": service_name,
                "negative_response_code": nrc,
                "negative_response_code_hex": None if nrc is None else f"0x{nrc:02X}",
                "negative_response_name": nrc_name,
                "response_pending": nrc == 0x78,
            }
        )
        _put_data(fields, "negative_response_data", payload[3:])
        nrc_text = "??" if nrc is None else f"{nrc:02X}"
        return DecodedMessage(
            message=message,
            protocol=ProtocolKind.UDS,
            name=f"UDS NEG {service_name} — NRC 0x{nrc_text} {nrc_name}",
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
    def _decode_common_subfunction(
        payload: bytes,
        base_sid: int,
        response_type: str,
        fields: dict[str, Any],
    ) -> int | None:
        if base_sid not in UDS_SUBFUNCTION_SERVICES or len(payload) < 2:
            return None
        raw = payload[1]
        subfunction = raw & 0x7F
        fields["subfunction_raw"] = raw
        fields["subfunction"] = subfunction
        fields["subfunction_hex"] = f"0x{subfunction:02X}"
        fields["suppress_positive_response"] = bool(raw & 0x80) if response_type == "request" else False
        return subfunction

    def _decode_service_data(
        self,
        payload: bytes,
        base_sid: int,
        response_type: str,
        subfunction: int | None,
        fields: dict[str, Any],
    ) -> None:
        if base_sid == 0x10:
            self._decode_session_control(payload, response_type, fields)
        elif base_sid == 0x11:
            self._decode_ecu_reset(payload, response_type, fields)
        elif base_sid == 0x14:
            self._decode_clear_dtc(payload, response_type, fields)
        elif base_sid == 0x19:
            self._decode_read_dtc(payload, response_type, subfunction, fields)
        elif base_sid == 0x22:
            self._decode_read_did(payload, response_type, fields)
        elif base_sid == 0x23:
            self._decode_read_memory(payload, response_type, fields)
        elif base_sid == 0x24:
            self._decode_scaling_did(payload, fields)
        elif base_sid == 0x27:
            self._decode_security_access(payload, response_type, subfunction, fields)
        elif base_sid == 0x28:
            self._decode_communication_control(payload, fields)
        elif base_sid == 0x2A:
            self._decode_periodic_did(payload, response_type, fields)
        elif base_sid == 0x2C:
            self._decode_dynamic_did(payload, fields)
        elif base_sid == 0x2E:
            self._decode_write_did(payload, response_type, fields)
        elif base_sid == 0x2F:
            self._decode_io_control(payload, response_type, fields)
        elif base_sid == 0x31:
            self._decode_routine_control(payload, response_type, fields)
        elif base_sid in (0x34, 0x35):
            self._decode_request_transfer(payload, response_type, fields)
        elif base_sid == 0x36:
            self._decode_transfer_data(payload, response_type, fields)
        elif base_sid == 0x37:
            _put_data(
                fields,
                "transfer_response_parameter_record"
                if response_type == "positive-response"
                else "transfer_request_parameter_record",
                payload[1:],
            )
        elif base_sid == 0x38:
            if len(payload) >= 2:
                fields["mode_of_operation"] = payload[1]
                fields["mode_of_operation_hex"] = f"0x{payload[1]:02X}"
            _put_data(fields, "file_transfer_parameter_record", payload[2:])
        elif base_sid == 0x3D:
            self._decode_write_memory(payload, response_type, fields)
        elif base_sid in (0x29, 0x83, 0x84, 0x85, 0x86, 0x87):
            _put_data(fields, "parameter_record", payload[2:] if subfunction is not None else payload[1:])
        elif base_sid == 0x3E:
            _put_data(fields, "tester_present_data", payload[2:])
        else:
            _put_data(fields, "service_data", payload[1:])

    @staticmethod
    def _decode_session_control(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if len(payload) >= 2:
            fields["diagnostic_session_type"] = payload[1] & 0x7F
            fields["diagnostic_session_type_hex"] = f"0x{payload[1] & 0x7F:02X}"
        if response_type == "positive-response" and len(payload) >= 6:
            fields["p2_server_max_ms"] = int.from_bytes(payload[2:4], "big")
            fields["p2_star_server_max_ms"] = int.from_bytes(payload[4:6], "big") * 10
            _put_data(fields, "session_parameter_record", payload[6:])
        elif len(payload) > 2:
            _put_data(fields, "session_parameter_record", payload[2:])

    @staticmethod
    def _decode_ecu_reset(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if len(payload) >= 2:
            fields["reset_type"] = payload[1] & 0x7F
            fields["reset_type_hex"] = f"0x{payload[1] & 0x7F:02X}"
        if response_type == "positive-response" and len(payload) >= 3:
            fields["power_down_time_s"] = payload[2]
            _put_data(fields, "reset_status_record", payload[3:])
        else:
            _put_data(fields, "reset_option_record", payload[2:])

    @staticmethod
    def _decode_clear_dtc(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if response_type == "request" and len(payload) >= 4:
            group = int.from_bytes(payload[1:4], "big")
            fields["group_of_dtc"] = group
            fields["group_of_dtc_hex"] = f"0x{group:06X}"
            _put_data(fields, "clear_dtc_option_record", payload[4:])
        else:
            _put_data(fields, "clear_dtc_response_record", payload[1:])

    @staticmethod
    def _decode_read_dtc(
        payload: bytes,
        response_type: str,
        subfunction: int | None,
        fields: dict[str, Any],
    ) -> None:
        fields["dtc_subfunction"] = subfunction
        if subfunction is None:
            _put_data(fields, "dtc_data", payload[1:])
            return
        if response_type == "request":
            if len(payload) >= 3 and subfunction in {0x01, 0x02, 0x0F, 0x11, 0x12, 0x13, 0x15}:
                fields["dtc_status_mask"] = payload[2]
                fields["dtc_status_mask_hex"] = f"0x{payload[2]:02X}"
            if len(payload) >= 5 and subfunction in {0x04, 0x06, 0x10}:
                dtc = int.from_bytes(payload[2:5], "big")
                fields["dtc"] = dtc
                fields["dtc_hex"] = f"0x{dtc:06X}"
            _put_data(fields, "dtc_request_record", payload[2:])
            return

        if subfunction in {0x01, 0x07, 0x11, 0x12} and len(payload) >= 6:
            fields["dtc_status_availability_mask"] = payload[2]
            fields["dtc_format_identifier"] = payload[3]
            fields["dtc_count"] = int.from_bytes(payload[4:6], "big")
            _put_data(fields, "dtc_response_record", payload[6:])
            return

        if subfunction in {0x02, 0x0A, 0x0F, 0x13, 0x15} and len(payload) >= 3:
            fields["dtc_status_availability_mask"] = payload[2]
            raw_entries = payload[3:]
            entries: list[dict[str, Any]] = []
            for offset in range(0, len(raw_entries) - 3, 4):
                chunk = raw_entries[offset : offset + 4]
                dtc = int.from_bytes(chunk[:3], "big")
                entries.append(
                    {
                        "dtc": dtc,
                        "dtc_hex": f"0x{dtc:06X}",
                        "status": chunk[3],
                        "status_hex": f"0x{chunk[3]:02X}",
                    }
                )
            fields["dtc_entries"] = entries
            fields["dtc_count"] = len(entries)
            if entries:
                fields["dtc_summary"] = ", ".join(
                    f"{item['dtc_hex']}/{item['status_hex']}" for item in entries[:6]
                )
            trailing = raw_entries[len(entries) * 4 :]
            _put_data(fields, "dtc_trailing_data", trailing)
            return

        _put_data(fields, "dtc_response_record", payload[2:])

    @staticmethod
    def _decode_read_did(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        data = payload[1:]
        if response_type == "request":
            dids = [int.from_bytes(data[offset : offset + 2], "big") for offset in range(0, len(data) - 1, 2)]
            fields["did_list"] = dids
            fields["did_list_hex"] = ", ".join(f"0x{did:04X}" for did in dids)
            fields["did_count"] = len(dids)
            if dids:
                fields["did"] = dids[0]
                fields["did_hex"] = f"0x{dids[0]:04X}"
            if len(data) % 2:
                _put_data(fields, "did_trailing_data", data[-1:])
            return
        if len(payload) >= 3:
            did = int.from_bytes(payload[1:3], "big")
            fields["did"] = did
            fields["did_hex"] = f"0x{did:04X}"
            _put_data(fields, "data_record", payload[3:])
            fields["did_segmentation"] = "first-did-with-remaining-data"
        else:
            _put_data(fields, "data_record", payload[1:])

    @staticmethod
    def _decode_read_memory(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if response_type == "request":
            _decode_address_and_size(payload, 1, fields)
        else:
            _put_data(fields, "data_record", payload[1:])

    @staticmethod
    def _decode_scaling_did(payload: bytes, fields: dict[str, Any]) -> None:
        if len(payload) >= 3:
            did = int.from_bytes(payload[1:3], "big")
            fields["did"] = did
            fields["did_hex"] = f"0x{did:04X}"
            _put_data(fields, "scaling_data_record", payload[3:])
        else:
            _put_data(fields, "scaling_data_record", payload[1:])

    @staticmethod
    def _decode_security_access(
        payload: bytes,
        response_type: str,
        subfunction: int | None,
        fields: dict[str, Any],
    ) -> None:
        if subfunction is None:
            _put_data(fields, "security_data", payload[1:])
            return
        level = (subfunction + 1) // 2
        fields["security_level"] = level
        data = payload[2:]
        if subfunction % 2:
            fields["security_access_type"] = "request-seed"
            if response_type == "positive-response":
                _put_data(fields, "seed", data)
            else:
                _put_data(fields, "seed_request_data", data)
        else:
            fields["security_access_type"] = "send-key"
            if response_type == "request":
                _put_data(fields, "key", data)
            else:
                _put_data(fields, "security_response_data", data)

    @staticmethod
    def _decode_communication_control(payload: bytes, fields: dict[str, Any]) -> None:
        if len(payload) >= 2:
            fields["control_type"] = payload[1] & 0x7F
            fields["control_type_hex"] = f"0x{payload[1] & 0x7F:02X}"
        if len(payload) >= 3:
            fields["communication_type"] = payload[2]
            fields["communication_type_hex"] = f"0x{payload[2]:02X}"
        _put_data(fields, "communication_control_record", payload[3:])

    @staticmethod
    def _decode_periodic_did(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if len(payload) >= 2:
            fields["transmission_mode"] = payload[1]
            fields["transmission_mode_hex"] = f"0x{payload[1]:02X}"
        periodic_ids = list(payload[2:])
        if periodic_ids:
            fields["periodic_identifier_list"] = periodic_ids
            fields["periodic_identifier_list_hex"] = ", ".join(
                f"0x{item:02X}" for item in periodic_ids
            )
        if response_type == "positive-response":
            _put_data(fields, "periodic_response_record", payload[2:])

    @staticmethod
    def _decode_dynamic_did(payload: bytes, fields: dict[str, Any]) -> None:
        if len(payload) >= 4:
            did = int.from_bytes(payload[2:4], "big")
            fields["dynamically_defined_did"] = did
            fields["dynamically_defined_did_hex"] = f"0x{did:04X}"
            _put_data(fields, "dynamic_definition_record", payload[4:])
        else:
            _put_data(fields, "dynamic_definition_record", payload[2:])

    @staticmethod
    def _decode_write_did(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if len(payload) >= 3:
            did = int.from_bytes(payload[1:3], "big")
            fields["did"] = did
            fields["did_hex"] = f"0x{did:04X}"
            if response_type == "request":
                _put_data(fields, "data_record", payload[3:])
            elif len(payload) > 3:
                _put_data(fields, "write_response_record", payload[3:])
        else:
            _put_data(fields, "data_record", payload[1:])

    @staticmethod
    def _decode_io_control(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if len(payload) < 3:
            _put_data(fields, "io_control_record", payload[1:])
            return
        did = int.from_bytes(payload[1:3], "big")
        fields["did"] = did
        fields["did_hex"] = f"0x{did:04X}"
        if response_type == "request" and len(payload) >= 4:
            fields["io_control_parameter"] = payload[3]
            fields["io_control_parameter_hex"] = f"0x{payload[3]:02X}"
            _put_data(fields, "control_state_record", payload[4:])
        else:
            _put_data(fields, "control_status_record", payload[3:])

    @staticmethod
    def _decode_routine_control(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if len(payload) >= 4:
            routine_id = int.from_bytes(payload[2:4], "big")
            fields["routine_id"] = routine_id
            fields["routine_id_hex"] = f"0x{routine_id:04X}"
            _put_data(
                fields,
                "routine_status_record"
                if response_type == "positive-response"
                else "routine_option_record",
                payload[4:],
            )
        else:
            _put_data(fields, "routine_record", payload[2:])

    @staticmethod
    def _decode_request_transfer(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if response_type == "request":
            if len(payload) < 3:
                _put_data(fields, "transfer_request_record", payload[1:])
                return
            dfi = payload[1]
            fields["data_format_identifier"] = dfi
            fields["compression_method"] = (dfi >> 4) & 0x0F
            fields["encryption_method"] = dfi & 0x0F
            _decode_address_and_size(payload, 2, fields)
            return
        if len(payload) < 2:
            return
        length_format_identifier = payload[1]
        max_length_size = (length_format_identifier >> 4) & 0x0F
        fields["length_format_identifier"] = length_format_identifier
        fields["max_number_of_block_length_size"] = max_length_size
        fields["length_format_reserved_nibble"] = length_format_identifier & 0x0F
        end = 2 + max_length_size
        if max_length_size and len(payload) >= end:
            fields["max_number_of_block_length"] = int.from_bytes(payload[2:end], "big")
        _put_data(fields, "transfer_response_record", payload[end:])

    @staticmethod
    def _decode_transfer_data(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if len(payload) >= 2:
            fields["block_sequence_counter"] = payload[1]
            fields["block_sequence_counter_hex"] = f"0x{payload[1]:02X}"
        _put_data(
            fields,
            "transfer_response_parameter_record"
            if response_type == "positive-response"
            else "transfer_data",
            payload[2:],
        )

    @staticmethod
    def _decode_write_memory(
        payload: bytes,
        response_type: str,
        fields: dict[str, Any],
    ) -> None:
        if response_type == "positive-response":
            _decode_address_and_size(payload, 1, fields)
            return
        data_offset = _decode_address_and_size(payload, 1, fields)
        if data_offset is not None:
            _put_data(fields, "data_record", payload[data_offset:])

    @staticmethod
    def _summary_suffix(fields: dict[str, Any]) -> str:
        if fields.get("did_hex"):
            return f" DID {fields['did_hex']}"
        if fields.get("routine_id_hex"):
            return f" RID {fields['routine_id_hex']}"
        if fields.get("security_level") is not None:
            access_type = fields.get("security_access_type", "security")
            return f" level {fields['security_level']} {access_type}"
        if fields.get("block_sequence_counter") is not None:
            return f" block {fields['block_sequence_counter']}"
        if fields.get("subfunction_hex"):
            return f" sub {fields['subfunction_hex']}"
        return ""


def _decode_address_and_size(
    payload: bytes,
    alfid_offset: int,
    fields: dict[str, Any],
) -> int | None:
    if len(payload) <= alfid_offset:
        return None
    alfid = payload[alfid_offset]
    address_length = alfid & 0x0F
    size_length = (alfid >> 4) & 0x0F
    fields["address_and_length_format_identifier"] = alfid
    fields["address_and_length_format_identifier_hex"] = f"0x{alfid:02X}"
    fields["memory_address_length"] = address_length
    fields["memory_size_length"] = size_length
    cursor = alfid_offset + 1
    required = cursor + address_length + size_length
    if address_length == 0 or size_length == 0 or len(payload) < required:
        fields["malformed_address_and_length_record"] = True
        _put_data(fields, "address_and_length_data", payload[cursor:])
        return None
    address_bytes = payload[cursor : cursor + address_length]
    cursor += address_length
    size_bytes = payload[cursor : cursor + size_length]
    cursor += size_length
    address = int.from_bytes(address_bytes, "big")
    size = int.from_bytes(size_bytes, "big")
    fields["memory_address"] = address
    fields["memory_address_hex"] = f"0x{address:0{address_length * 2}X}"
    fields["memory_size"] = size
    fields["memory_size_hex"] = f"0x{size:0{size_length * 2}X}"
    return cursor


def _put_data(fields: dict[str, Any], prefix: str, data: bytes) -> None:
    raw = bytes(data)
    fields[f"{prefix}_length"] = len(raw)
    if not raw:
        return
    fields[f"{prefix}_hex"] = _hex(raw)
    ascii_text = _printable_ascii(raw)
    if ascii_text is not None:
        fields[f"{prefix}_ascii"] = ascii_text


def _hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def _printable_ascii(data: bytes) -> str | None:
    if len(data) < 3 or any(byte < 0x20 or byte > 0x7E for byte in data):
        return None
    return data.decode("ascii")
