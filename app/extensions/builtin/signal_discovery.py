from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.domain import Artifact, ArtifactSource
from app.models import CanFrame

from ..contracts import AnalysisContext
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType


SIGNAL_DISCOVERY_PROVIDER_ID = "crt.analysis.signal_discovery_activity"
SIGNAL_DISCOVERY_PROVIDER_VERSION = "1.0.0"
SIGNAL_DISCOVERY_ALGORITHM_VERSION = "1"
SIGNAL_DISCOVERY_ARTIFACT_SCHEMA_VERSION = 1
DEFAULT_SAMPLE_LIMIT = 5_000
MAX_SAMPLE_LIMIT = 20_000
_PROGRESS_STRIDE = 4096


@dataclass(frozen=True, slots=True)
class MessageKey:
    channel: int
    arbitration_id: int
    is_extended_id: bool
    frame_kind: str = "data"

    def __post_init__(self) -> None:
        if self.channel < 0:
            raise ValueError("channel cannot be negative")
        maximum_id = 0x1FFFFFFF if self.is_extended_id else 0x7FF
        if not 0 <= self.arbitration_id <= maximum_id:
            raise ValueError("arbitration_id is outside the selected CAN ID range")
        if self.frame_kind not in {"data", "remote", "error"}:
            raise ValueError("frame_kind must be data, remote or error")

    def matches(self, frame: CanFrame) -> bool:
        return (
            frame.channel == self.channel
            and frame.arbitration_id == self.arbitration_id
            and frame.is_extended_id == self.is_extended_id
            and _frame_kind(frame) == self.frame_kind
        )

    def to_payload(self) -> dict[str, Any]:
        width = 8 if self.is_extended_id else 3
        return {
            "channel": self.channel,
            "arbitration_id": self.arbitration_id,
            "arbitration_id_hex": f"{self.arbitration_id:0{width}X}",
            "is_extended_id": self.is_extended_id,
            "frame_kind": self.frame_kind,
        }


@dataclass(slots=True)
class _ByteActivity:
    index: int
    present_count: int = 0
    missing_count: int = 0
    change_count: int = 0
    first_value: int | None = None
    last_value: int | None = None
    min_value: int | None = None
    max_value: int | None = None
    min_source_row: int | None = None
    max_source_row: int | None = None
    first_source_row: int | None = None
    last_source_row: int | None = None
    unique_values: set[int] = field(default_factory=set)
    bit_set_counts: list[int] = field(default_factory=lambda: [0] * 8)
    bit_transition_counts: list[int] = field(default_factory=lambda: [0] * 8)
    _previous_value: int | None = None

    def add(self, source_row: int, value: int) -> None:
        if not 0 <= value <= 0xFF:
            raise ValueError("byte value must be in range 0..255")
        if self.present_count == 0:
            self.first_value = value
            self.first_source_row = source_row
        elif self._previous_value is not None:
            if value != self._previous_value:
                self.change_count += 1
            changed = value ^ self._previous_value
            for bit in range(8):
                if changed & (1 << bit):
                    self.bit_transition_counts[bit] += 1

        self.present_count += 1
        self.last_value = value
        self.last_source_row = source_row
        self.unique_values.add(value)
        if self.min_value is None or value < self.min_value:
            self.min_value = value
            self.min_source_row = source_row
        if self.max_value is None or value > self.max_value:
            self.max_value = value
            self.max_source_row = source_row
        for bit in range(8):
            if value & (1 << bit):
                self.bit_set_counts[bit] += 1
        self._previous_value = value

    def mark_missing(self) -> None:
        self.missing_count += 1
        # Do not count a transition across a frame where this byte did not exist.
        self._previous_value = None

    def to_payload(self) -> dict[str, Any]:
        transition_denominator = max(0, self.present_count - 1)
        bits = []
        for bit in range(8):
            set_count = self.bit_set_counts[bit]
            bits.append(
                {
                    "bit": bit,
                    "set_count": set_count,
                    "clear_count": self.present_count - set_count,
                    "set_ratio": _ratio(set_count, self.present_count),
                    "transition_count": self.bit_transition_counts[bit],
                    "transition_rate": _ratio(
                        self.bit_transition_counts[bit], transition_denominator
                    ),
                    "constant": (
                        self.present_count > 0
                        and (set_count == 0 or set_count == self.present_count)
                    ),
                }
            )
        return {
            "byte": self.index,
            "present_count": self.present_count,
            "missing_count": self.missing_count,
            "first_value": self.first_value,
            "last_value": self.last_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "unique_value_count": len(self.unique_values),
            "change_count": self.change_count,
            "change_rate": _ratio(self.change_count, transition_denominator),
            "first_source_row": self.first_source_row,
            "last_source_row": self.last_source_row,
            "min_source_row": self.min_source_row,
            "max_source_row": self.max_source_row,
            "bits": bits,
        }


class SignalDiscoveryActivityProvider:
    """Exact byte/bit activity for one raw CAN message key plus bounded evidence samples."""

    manifest = ExtensionManifest(
        id=SIGNAL_DISCOVERY_PROVIDER_ID,
        name="Signal Discovery — aktywność bitów/bajtów",
        version=SIGNAL_DISCOVERY_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.ANALYSIS,
        inputs=("session",),
        outputs=("signal_discovery_activity",),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.SESSION_READ,
            ExtensionPermission.ARTIFACT_WRITE,
        ),
    )

    algorithm_version = SIGNAL_DISCOVERY_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input = _single_session_input(context)
        key = message_key_from_parameters(analysis_input.parameters)
        sample_limit = _sample_limit(analysis_input.parameters)
        source = context.project.session(analysis_input.source_id)
        expected_frames = source.frames.frame_count
        progress_total = expected_frames * 2 + 1
        context.progress.report(0, progress_total, "analiza aktywności wybranego klucza")

        byte_activity: list[_ByteActivity] = []
        matching_count = 0
        first_source_row: int | None = None
        last_source_row: int | None = None
        min_dlc: int | None = None
        max_dlc: int | None = None

        for source_row, frame in enumerate(source.frames.iter_frames()):
            if key.matches(frame):
                if matching_count == 0:
                    first_source_row = source_row
                matching_count += 1
                last_source_row = source_row
                min_dlc = frame.dlc if min_dlc is None else min(min_dlc, frame.dlc)
                max_dlc = frame.dlc if max_dlc is None else max(max_dlc, frame.dlc)
                while len(byte_activity) < frame.dlc:
                    accumulator = _ByteActivity(index=len(byte_activity))
                    # Earlier matching frames did not contain this newly observed byte.
                    accumulator.missing_count = matching_count - 1
                    byte_activity.append(accumulator)
                for index, accumulator in enumerate(byte_activity):
                    if index < frame.dlc:
                        accumulator.add(source_row, frame.data[index])
                    else:
                        accumulator.mark_missing()

            processed = source_row + 1
            if processed % _PROGRESS_STRIDE == 0 or processed == expected_frames:
                context.progress.report(
                    processed,
                    progress_total,
                    f"przebieg 1/2: {processed} ramek",
                )

        context.cancellation.raise_if_cancelled()
        target_occurrences = _sample_occurrences(matching_count, sample_limit)
        samples: list[dict[str, Any]] = []
        occurrence = 0
        target_index = 0

        for source_row, frame in enumerate(source.frames.iter_frames()):
            if key.matches(frame):
                if (
                    target_index < len(target_occurrences)
                    and occurrence == target_occurrences[target_index]
                ):
                    samples.append(
                        {
                            "source_row": source_row,
                            "sequence": frame.sequence,
                            "timestamp_ns": frame.timestamp_ns,
                            "dlc": frame.dlc,
                            "data": list(frame.data),
                            "data_hex": frame.data_hex,
                        }
                    )
                    target_index += 1
                occurrence += 1

            processed = expected_frames + source_row + 1
            if (source_row + 1) % _PROGRESS_STRIDE == 0 or source_row + 1 == expected_frames:
                context.progress.report(
                    processed,
                    progress_total,
                    f"przebieg 2/2: próbka {len(samples)}/{len(target_occurrences)}",
                )

        payload = {
            "schema": "crt.signal_discovery_activity",
            "schema_version": SIGNAL_DISCOVERY_ARTIFACT_SCHEMA_VERSION,
            "generated_by": {
                "provider_id": self.manifest.id,
                "provider_version": self.manifest.version,
                "algorithm_version": self.algorithm_version,
                "crt_api": self.manifest.crt_api,
            },
            "project": {
                "id": context.project.project_id,
                "name": context.project.project_name,
            },
            "session": {
                "id": source.id,
                "name": source.name,
                "sha256": source.sha256,
                "frame_count": source.frame_count,
            },
            "message_key": key.to_payload(),
            "summary": {
                "matching_frame_count": matching_count,
                "first_source_row": first_source_row,
                "last_source_row": last_source_row,
                "min_dlc": min_dlc,
                "max_dlc": max_dlc,
                "variable_dlc": min_dlc is not None and max_dlc is not None and min_dlc != max_dlc,
                "byte_count_observed": len(byte_activity),
            },
            "bytes": [item.to_payload() for item in byte_activity],
            "sample": {
                "bounded": matching_count > len(samples),
                "limit": sample_limit,
                "matching_frame_count": matching_count,
                "sampled_frame_count": len(samples),
                "strategy": "evenly-spaced-occurrence-index",
                "frames": samples,
            },
        }

        artifact = context.artifact_writer.write_json(
            filename="signal-discovery-activity.json",
            artifact_type="signal_discovery_activity",
            schema_version=SIGNAL_DISCOVERY_ARTIFACT_SCHEMA_VERSION,
            sources=(
                ArtifactSource(
                    session_id=source.id,
                    source_kind="session",
                    source_reference={
                        "sha256": source.sha256,
                        "message_key": key.to_payload(),
                        "matching_frame_count": matching_count,
                    },
                ),
            ),
            payload=payload,
            metadata={
                "session_id": source.id,
                "message_key": key.to_payload(),
                "matching_frame_count": matching_count,
                "sampled_frame_count": len(samples),
            },
        )
        context.progress.report(progress_total, progress_total, "zapisano Signal Discovery")
        return artifact


def message_key_from_parameters(parameters: Mapping[str, Any]) -> MessageKey:
    try:
        channel = int(parameters.get("channel", 0))
        arbitration_id = _parse_arbitration_id(parameters.get("arbitration_id"))
        is_extended_id = _parse_bool(parameters.get("is_extended_id", False))
        frame_kind = str(parameters.get("frame_kind", "data")).strip().lower()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid Signal Discovery message key: {exc}") from exc
    return MessageKey(
        channel=channel,
        arbitration_id=arbitration_id,
        is_extended_id=is_extended_id,
        frame_kind=frame_kind,
    )


def extract_bitfield(
    data: bytes | bytearray | Sequence[int],
    *,
    start_bit: int,
    length: int,
    byte_order: str = "intel",
    signed: bool = False,
) -> int | None:
    """Decode an arbitrary raw field using DBC-compatible Intel/Motorola bit numbering.

    Intel: start_bit is the least-significant bit and positions increase linearly.
    Motorola: start_bit is the most-significant bit using the CANdb++ saw-tooth rule.
    None is returned when the selected field is not fully present in the payload.
    """

    payload = bytes(data)
    if start_bit < 0:
        raise ValueError("start_bit cannot be negative")
    if not 1 <= length <= 64:
        raise ValueError("length must be in range 1..64")
    normalized_order = str(byte_order).strip().lower()
    if normalized_order not in {"intel", "motorola"}:
        raise ValueError("byte_order must be intel or motorola")

    if normalized_order == "intel":
        if start_bit + length > len(payload) * 8:
            return None
        raw = int.from_bytes(payload, byteorder="little", signed=False)
        value = (raw >> start_bit) & ((1 << length) - 1)
    else:
        bit_index = start_bit
        value = 0
        for _ in range(length):
            byte_index = bit_index // 8
            bit_in_byte = bit_index % 8
            if not 0 <= byte_index < len(payload):
                return None
            value = (value << 1) | ((payload[byte_index] >> bit_in_byte) & 1)
            if bit_in_byte == 0:
                bit_index += 15
            else:
                bit_index -= 1

    if signed and value & (1 << (length - 1)):
        value -= 1 << length
    return value


def bitfield_series_from_sample(
    frames: Sequence[Mapping[str, Any]],
    *,
    start_bit: int,
    length: int,
    byte_order: str,
    signed: bool,
    scale: float = 1.0,
    offset: float = 0.0,
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for frame in frames:
        raw = extract_bitfield(
            frame.get("data", ()),
            start_bit=start_bit,
            length=length,
            byte_order=byte_order,
            signed=signed,
        )
        if raw is None:
            continue
        result.append(
            {
                "source_row": int(frame["source_row"]),
                "sequence": int(frame["sequence"]),
                "timestamp_ns": int(frame["timestamp_ns"]),
                "raw": raw,
                "value": float(raw) * float(scale) + float(offset),
            }
        )
    return tuple(result)


def _single_session_input(context: AnalysisContext):
    if len(context.inputs) != 1 or context.inputs[0].kind != "session":
        raise ValueError("Signal Discovery requires exactly one session input")
    return context.inputs[0]


def _parse_arbitration_id(value: Any) -> int:
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            raise ValueError("arbitration_id cannot be empty")
        if text.startswith("0x"):
            return int(text, 16)
        # CAN IDs are normally entered in hexadecimal in CRT; accept pure decimal
        # only when explicitly digit-only.
        return int(text, 10) if text.isdigit() else int(text, 16)
    if value is None:
        raise ValueError("arbitration_id is required")
    return int(value)


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "ext", "extended"}:
            return True
        if normalized in {"0", "false", "no", "off", "std", "standard"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    raise ValueError(f"cannot parse boolean value: {value!r}")


def _sample_limit(parameters: Mapping[str, Any]) -> int:
    value = int(parameters.get("sample_limit", DEFAULT_SAMPLE_LIMIT))
    if not 2 <= value <= MAX_SAMPLE_LIMIT:
        raise ValueError(f"sample_limit must be in range 2..{MAX_SAMPLE_LIMIT}")
    return value


def _sample_occurrences(count: int, limit: int) -> tuple[int, ...]:
    if count <= 0:
        return ()
    if count <= limit:
        return tuple(range(count))
    if limit == 1:
        return (0,)
    return tuple((index * (count - 1)) // (limit - 1) for index in range(limit))


def _frame_kind(frame: CanFrame) -> str:
    if frame.is_error_frame:
        return "error"
    if frame.is_remote_frame:
        return "remote"
    return "data"


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


__all__ = [
    "DEFAULT_SAMPLE_LIMIT",
    "MAX_SAMPLE_LIMIT",
    "MessageKey",
    "SIGNAL_DISCOVERY_ALGORITHM_VERSION",
    "SIGNAL_DISCOVERY_ARTIFACT_SCHEMA_VERSION",
    "SIGNAL_DISCOVERY_PROVIDER_ID",
    "SIGNAL_DISCOVERY_PROVIDER_VERSION",
    "SignalDiscoveryActivityProvider",
    "bitfield_series_from_sample",
    "extract_bitfield",
    "message_key_from_parameters",
]
