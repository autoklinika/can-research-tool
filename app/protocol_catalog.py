from __future__ import annotations


J1939_PGN_NAMES: dict[int, str] = {
    0x00EA00: "Request",
    0x00EB00: "Transport Protocol Data Transfer",
    0x00EC00: "Transport Protocol Connection Management",
    0x00EE00: "Address Claimed",
    0x00FECA: "Active Diagnostic Trouble Codes (DM1)",
    0x00FECB: "Previously Active Diagnostic Trouble Codes (DM2)",
}


UDS_SERVICE_NAMES: dict[int, str] = {
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
    0x38: "RequestFileTransfer",
    0x3D: "WriteMemoryByAddress",
    0x3E: "TesterPresent",
    0x83: "AccessTimingParameter",
    0x84: "SecuredDataTransmission",
    0x85: "ControlDTCSetting",
    0x86: "ResponseOnEvent",
    0x87: "LinkControl",
}


UDS_NRC_NAMES: dict[int, str] = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x14: "responseTooLong",
    0x21: "busyRepeatRequest",
    0x22: "conditionsNotCorrect",
    0x24: "requestSequenceError",
    0x25: "noResponseFromSubnetComponent",
    0x26: "failurePreventsExecutionOfRequestedAction",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceedNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x70: "uploadDownloadNotAccepted",
    0x71: "transferDataSuspended",
    0x72: "generalProgrammingFailure",
    0x73: "wrongBlockSequenceCounter",
    0x78: "requestCorrectlyReceivedResponsePending",
    0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
    0x81: "rpmTooHigh",
    0x82: "rpmTooLow",
    0x83: "engineIsRunning",
    0x84: "engineIsNotRunning",
    0x85: "engineRunTimeTooLow",
    0x86: "temperatureTooHigh",
    0x87: "temperatureTooLow",
    0x88: "vehicleSpeedTooHigh",
    0x89: "vehicleSpeedTooLow",
    0x8A: "throttlePedalTooHigh",
    0x8B: "throttlePedalTooLow",
    0x8C: "transmissionRangeNotInNeutral",
    0x8D: "transmissionRangeNotInGear",
    0x8F: "brakeSwitchNotClosed",
    0x90: "shifterLeverNotInPark",
    0x91: "torqueConverterClutchLocked",
    0x92: "voltageTooHigh",
    0x93: "voltageTooLow",
}


UDS_SUBFUNCTION_SERVICES = {
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

UDS_DID_SERVICES = {0x22, 0x2E, 0x2F}


def j1939_pgn_name(pgn: int | None) -> str:
    if pgn is None:
        return "Unknown PGN"
    return J1939_PGN_NAMES.get(pgn, f"PGN 0x{pgn:05X}")


def uds_service_name(service_id: int | None) -> str:
    if service_id is None:
        return "UnknownService"
    return UDS_SERVICE_NAMES.get(service_id, f"Service0x{service_id:02X}")


def uds_nrc_name(nrc: int | None) -> str:
    if nrc is None:
        return "unknownNRC"
    return UDS_NRC_NAMES.get(nrc, f"NRC0x{nrc:02X}")
