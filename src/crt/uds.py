from __future__ import annotations

from dataclasses import dataclass

from .models import DecodedEvent, IsoTpMessage
from .sac import SAC_PROFILE, SacProfile


_SERVICE_NAMES = {
    0x10: "DiagnosticSessionControl",
    0x22: "ReadDataByIdentifier",
    0x3E: "TesterPresent",
    0x50: "DiagnosticSessionControl positive response",
    0x62: "ReadDataByIdentifier positive response",
    0x7F: "NegativeResponse",
}

_NRC_NAMES = {
    0x10: "General reject",
    0x11: "Service not supported",
    0x12: "Sub-function not supported",
    0x13: "Incorrect message length or format",
    0x22: "Conditions not correct",
    0x31: "Request out of range",
    0x33: "Security access denied",
    0x35: "Invalid key",
    0x36: "Exceeded number of attempts",
    0x37: "Required time delay not expired",
    0x78: "Response pending",
}


@dataclass(slots=True)
class UdsDecoder:
    profile: SacProfile = SAC_PROFILE

    def decode(self, message: IsoTpMessage) -> DecodedEvent | None:
        payload = message.payload
        if not payload:
            return None

        service = payload[0]
        direction = self.profile.direction_for_id(message.arbitration_id)
        name = _SERVICE_NAMES.get(service, f"UDS service 0x{service:02X}")
        details = ""
        fields: dict[str, int | str] = {"service": service}

        if service in (0x10, 0x50) and len(payload) >= 2:
            session = payload[1]
            fields["session"] = session
            details = f"Session 0x{session:02X}"
        elif service in (0x22, 0x62) and len(payload) >= 3:
            did = (payload[1] << 8) | payload[2]
            did_name = self.profile.did_names.get(did, f"DID 0x{did:04X}")
            fields["did"] = did
            fields["did_name"] = did_name
            if service == 0x62:
                value = _decode_value(payload[3:])
                fields["value"] = value
                details = f"{did_name}: {value}"
            else:
                details = did_name
        elif service == 0x7F and len(payload) >= 3:
            rejected_service = payload[1]
            nrc = payload[2]
            fields["rejected_service"] = rejected_service
            fields["nrc"] = nrc
            details = (
                f"Service 0x{rejected_service:02X}, NRC 0x{nrc:02X} "
                f"({_NRC_NAMES.get(nrc, 'Unknown NRC')})"
            )
        elif len(payload) > 1:
            details = " ".join(f"{byte:02X}" for byte in payload[1:])

        return DecodedEvent(
            timestamp_s=message.completed_at_s,
            arbitration_id=message.arbitration_id,
            direction=direction,
            protocol="UDS/ISO-TP",
            name=name,
            details=details,
            payload=payload,
            fields=fields,
        )


def _decode_value(data: bytes) -> str:
    if not data:
        return "<empty>"
    printable = data.rstrip(b"\x00\xFF")
    if printable and all(0x20 <= byte <= 0x7E for byte in printable):
        return printable.decode("ascii")
    return " ".join(f"{byte:02X}" for byte in data)
