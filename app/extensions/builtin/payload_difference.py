from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from app.domain import Artifact, ArtifactSource
from app.models import CanFrame

from ..contracts import AnalysisContext, ComparisonContext, SessionSource
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType


PAYLOAD_DIFFERENCE_PROVIDER_ID = "crt.comparison.payload_difference"
PAYLOAD_DIFFERENCE_PROVIDER_VERSION = "1.0.0"
PAYLOAD_DIFFERENCE_ALGORITHM_VERSION = "1"
PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION = 1

_PROGRESS_STRIDE = 4096
_DEFAULT_MAXIMUM_VARIANTS_PER_MESSAGE_SESSION = 256
_DEFAULT_MAXIMUM_RANKED_CHANGES = 250
_DEFAULT_MINIMUM_MESSAGE_FRAME_COUNT = 1
_MAXIMUM_VARIANTS_LIMIT = 4096
_MAXIMUM_RANKED_CHANGES_LIMIT = 5000

MessageKey = tuple[int, int, bool, bool, bool]


@dataclass(slots=True)
class _ByteStats:
    observed_count: int = 0
    values: list[int] = field(default_factory=lambda: [0] * 256)

    def add(self, value: int) -> None:
        self.observed_count += 1
        self.values[value] += 1

    def payload(self, frame_count: int) -> dict[str, Any]:
        observed = [
            {
                "value": value,
                "value_hex": f"{value:02X}",
                "count": count,
                "share_percent": _round(count * 100 / self.observed_count),
            }
            for value, count in enumerate(self.values)
            if count
        ]
        return {
            "observed_count": self.observed_count,
            "presence_percent": _round(
                0.0 if not frame_count else self.observed_count * 100 / frame_count
            ),
            "unique_value_count": len(observed),
            "is_constant": len(observed) == 1,
            "constant_value": observed[0]["value"] if len(observed) == 1 else None,
            "constant_value_hex": (
                observed[0]["value_hex"] if len(observed) == 1 else None
            ),
            "values": observed,
        }


@dataclass(slots=True)
class _MessagePayloadStats:
    frame_count: int = 0
    dlc_counts: Counter[int] = field(default_factory=Counter)
    tracked_variants: Counter[bytes] = field(default_factory=Counter)
    untracked_variant_frame_count: int = 0
    byte_positions: list[_ByteStats] = field(default_factory=list)

    def add(self, frame: CanFrame, maximum_variants: int) -> None:
        self.frame_count += 1
        self.dlc_counts[len(frame.data)] += 1
        payload = bytes(frame.data)
        if payload in self.tracked_variants:
            self.tracked_variants[payload] += 1
        elif len(self.tracked_variants) < maximum_variants:
            self.tracked_variants[payload] = 1
        else:
            self.untracked_variant_frame_count += 1
        while len(self.byte_positions) < len(payload):
            self.byte_positions.append(_ByteStats())
        for index, value in enumerate(payload):
            self.byte_positions[index].add(value)

    def payload(self) -> dict[str, Any]:
        variants = sorted(
            (
                {
                    "payload_hex": payload.hex(" ").upper(),
                    "dlc": len(payload),
                    "count": count,
                    "share_percent": _round(count * 100 / self.frame_count),
                }
                for payload, count in self.tracked_variants.items()
            ),
            key=lambda item: (-int(item["count"]), str(item["payload_hex"])),
        )
        byte_positions = [
            {"index": index, **stats.payload(self.frame_count)}
            for index, stats in enumerate(self.byte_positions)
        ]
        constant_count = sum(1 for item in byte_positions if item["is_constant"])
        variable_count = sum(
            1 for item in byte_positions if int(item["unique_value_count"]) > 1
        )
        return {
            "frame_count": self.frame_count,
            "dlc_counts": [
                {"dlc": dlc, "count": count}
                for dlc, count in sorted(self.dlc_counts.items())
            ],
            "tracked_variant_count": len(variants),
            "tracked_variant_frame_count": sum(
                int(item["count"]) for item in variants
            ),
            "untracked_variant_frame_count": self.untracked_variant_frame_count,
            "variants_truncated": self.untracked_variant_frame_count > 0,
            "variants": variants,
            "byte_position_count": len(byte_positions),
            "constant_byte_position_count": constant_count,
            "variable_byte_position_count": variable_count,
            "byte_positions": byte_positions,
        }


@dataclass(slots=True)
class _SessionPayloadStats:
    source: SessionSource
    data_frame_count: int = 0
    skipped_non_data_frame_count: int = 0
    messages: dict[MessageKey, _MessagePayloadStats] = field(default_factory=dict)

    def add(self, frame: CanFrame, maximum_variants: int) -> None:
        if frame.is_remote_frame or frame.is_error_frame:
            self.skipped_non_data_frame_count += 1
            return
        self.data_frame_count += 1
        message = self.messages.setdefault(
            _message_key(frame),
            _MessagePayloadStats(),
        )
        message.add(frame, maximum_variants)

    def summary(self, baseline_keys: set[MessageKey], baseline_id: str) -> dict[str, Any]:
        own_keys = set(self.messages)
        is_base = self.source.id == baseline_id
        message_payloads = [message.payload() for message in self.messages.values()]
        return {
            "id": self.source.id,
            "name": self.source.name,
            "source": self.source.source,
            "status": self.source.status,
            "role": "base" if is_base else "compared",
            "declared_frame_count": self.source.frame_count,
            "reader_frame_count": self.source.frames.frame_count,
            "observed_data_frame_count": self.data_frame_count,
            "skipped_non_data_frame_count": self.skipped_non_data_frame_count,
            "payload_message_key_count": len(self.messages),
            "new_payload_message_key_count": 0 if is_base else len(own_keys - baseline_keys),
            "missing_payload_message_key_count": (
                0 if is_base else len(baseline_keys - own_keys)
            ),
            "tracked_payload_variant_count": sum(
                int(item["tracked_variant_count"]) for item in message_payloads
            ),
            "untracked_payload_variant_frame_count": sum(
                int(item["untracked_variant_frame_count"]) for item in message_payloads
            ),
            "constant_byte_position_count": sum(
                int(item["constant_byte_position_count"]) for item in message_payloads
            ),
            "variable_byte_position_count": sum(
                int(item["variable_byte_position_count"]) for item in message_payloads
            ),
            "sha256": self.source.sha256,
        }


class PayloadDifferenceProvider:
    """Deterministic passive comparison of CAN payload variants and byte positions."""

    manifest = ExtensionManifest(
        id=PAYLOAD_DIFFERENCE_PROVIDER_ID,
        name="CAN payload difference comparison",
        version=PAYLOAD_DIFFERENCE_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.COMPARISON,
        inputs=("comparison_set",),
        outputs=("comparison_payload_difference",),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.SESSION_READ,
            ExtensionPermission.ARTIFACT_WRITE,
        ),
    )
    algorithm_version = PAYLOAD_DIFFERENCE_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input, comparison = _comparison_input(context)
        if comparison.synchronization_mode != "none":
            raise ValueError(
                "payload difference Stage 2 supports only synchronization_mode none"
            )
        parameters = _parameters(analysis_input.parameters)
        sources = tuple(
            context.project.session(session_id) for session_id in comparison.session_ids
        )
        total_work = sum(source.frames.frame_count for source in sources) + 1
        context.progress.report(0, total_work, "reading immutable payload sessions")

        by_session: dict[str, _SessionPayloadStats] = {}
        processed = 0
        for source in sources:
            stats = _SessionPayloadStats(source)
            for frame in source.frames.iter_frames():
                context.cancellation.raise_if_cancelled()
                stats.add(
                    frame,
                    parameters["maximum_variants_per_message_session"],
                )
                processed += 1
                if processed % _PROGRESS_STRIDE == 0:
                    context.progress.report(
                        processed,
                        total_work,
                        f"analysed {processed} payload frames",
                    )
            by_session[source.id] = stats
            context.progress.report(
                processed,
                total_work,
                f"analysed payloads in session {source.name}",
            )

        baseline_id = comparison.base_session_id or comparison.session_ids[0]
        baseline = by_session[baseline_id]
        ordered = tuple(by_session[session_id] for session_id in comparison.session_ids)
        keys = sorted(
            {key for session in ordered for key in session.messages},
            key=_message_key_sort,
        )
        baseline_keys = set(baseline.messages)
        sessions = [session.summary(baseline_keys, baseline_id) for session in ordered]
        message_keys, notable, notable_count = _message_matrix(
            keys,
            ordered,
            baseline,
            parameters,
        )
        payload = {
            "schema": "crt.comparison_payload_difference",
            "schema_version": PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION,
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
            "input": {
                "kind": analysis_input.kind,
                "source_id": analysis_input.source_id,
                "parameters": parameters,
            },
            "comparison_set": {
                "id": comparison.id,
                "name": comparison.name,
                "session_ids": list(comparison.session_ids),
                "base_session_id": comparison.base_session_id,
                "effective_baseline_session_id": baseline_id,
                "synchronization_mode": comparison.synchronization_mode,
                "parameters": dict(comparison.parameters),
            },
            "summary": {
                "session_count": len(ordered),
                "baseline_session_id": baseline_id,
                "union_payload_message_key_count": len(keys),
                "common_payload_message_key_count": len(
                    set.intersection(*(set(session.messages) for session in ordered))
                ),
                "notable_change_count": notable_count,
                "returned_notable_change_count": len(notable),
                "notable_changes_truncated": notable_count > len(notable),
            },
            "sessions": sessions,
            "message_keys": message_keys,
            "notable_changes": notable,
        }
        artifact_sources = tuple(
            ArtifactSource(
                session_id=session.source.id,
                source_kind="session",
                source_reference={
                    "comparison_set_id": comparison.id,
                    "role": "base" if session.source.id == baseline_id else "compared",
                    "frame_count": session.source.frames.frame_count,
                    "data_frame_count": session.data_frame_count,
                    "sha256": session.source.sha256,
                },
            )
            for session in ordered
        )
        artifact = context.artifact_writer.write_json(
            filename="comparison-payload-difference.json",
            artifact_type="comparison_payload_difference",
            schema_version=PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION,
            sources=artifact_sources,
            payload=payload,
            metadata={
                "comparison_set_id": comparison.id,
                "baseline_session_id": baseline_id,
                "session_count": len(ordered),
                "payload_message_key_count": len(keys),
                "notable_change_count": notable_count,
            },
        )
        context.progress.report(total_work, total_work, "saved payload difference")
        return artifact


def _message_matrix(
    keys: list[MessageKey],
    sessions: tuple[_SessionPayloadStats, ...],
    baseline: _SessionPayloadStats,
    parameters: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    matrix: list[dict[str, Any]] = []
    notable: list[dict[str, Any]] = []
    session_order = {session.source.id: index for index, session in enumerate(sessions)}
    for key in keys:
        key_payload = _message_key_payload(key)
        baseline_message = baseline.messages.get(key)
        baseline_payload = (
            baseline_message.payload() if baseline_message is not None else None
        )
        session_rows: list[dict[str, Any]] = []
        for session in sessions:
            current_message = session.messages.get(key)
            current_payload = (
                current_message.payload() if current_message is not None else None
            )
            changes = _compare_message(
                key_payload,
                baseline.source.id,
                session,
                baseline_payload,
                current_payload,
                parameters,
            )
            session_rows.append(
                {
                    "session_id": session.source.id,
                    "session_name": session.source.name,
                    "role": (
                        "base" if session.source.id == baseline.source.id else "compared"
                    ),
                    "present": current_payload is not None,
                    "payload": current_payload,
                    "change_count": len(changes),
                }
            )
            notable.extend(changes)
        matrix.append(
            {
                **key_payload,
                "baseline": baseline_payload,
                "sessions": session_rows,
            }
        )
    notable.sort(
        key=lambda item: (
            session_order[str(item["session_id"])],
            _change_priority(str(item["change_type"])),
            int(item.get("byte_index", -1)),
            int(item["channel"]),
            bool(item["is_extended_id"]),
            int(item["arbitration_id"]),
            str(item.get("payload_hex", "")),
        )
    )
    count = len(notable)
    return matrix, notable[: parameters["maximum_ranked_changes"]], count


def _compare_message(
    key_payload: dict[str, Any],
    baseline_id: str,
    session: _SessionPayloadStats,
    baseline: dict[str, Any] | None,
    current: dict[str, Any] | None,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    if session.source.id == baseline_id:
        return []
    common = {
        **key_payload,
        "session_id": session.source.id,
        "session_name": session.source.name,
    }
    if baseline is None and current is not None:
        return [{**common, "change_type": "new_message_key"}]
    if baseline is not None and current is None:
        return [{**common, "change_type": "missing_message_key"}]
    if baseline is None or current is None:
        return []
    if (
        int(baseline["frame_count"]) < parameters["minimum_message_frame_count"]
        or int(current["frame_count"]) < parameters["minimum_message_frame_count"]
    ):
        return []

    changes: list[dict[str, Any]] = []
    baseline_dlc = {int(item["dlc"]) for item in baseline["dlc_counts"]}
    current_dlc = {int(item["dlc"]) for item in current["dlc_counts"]}
    if baseline_dlc != current_dlc:
        changes.append(
            {
                **common,
                "change_type": "dlc_set_changed",
                "baseline_dlc_counts": list(baseline["dlc_counts"]),
                "current_dlc_counts": list(current["dlc_counts"]),
            }
        )

    if baseline["variants_truncated"] or current["variants_truncated"]:
        changes.append(
            {
                **common,
                "change_type": "variant_comparison_truncated",
                "baseline_untracked_frame_count": baseline[
                    "untracked_variant_frame_count"
                ],
                "current_untracked_frame_count": current[
                    "untracked_variant_frame_count"
                ],
            }
        )
    else:
        baseline_variants = {
            str(item["payload_hex"]): item for item in baseline["variants"]
        }
        current_variants = {
            str(item["payload_hex"]): item for item in current["variants"]
        }
        for payload_hex in sorted(current_variants.keys() - baseline_variants.keys()):
            changes.append(
                {
                    **common,
                    "change_type": "new_payload_variant",
                    "payload_hex": payload_hex,
                    "current": current_variants[payload_hex],
                }
            )
        for payload_hex in sorted(baseline_variants.keys() - current_variants.keys()):
            changes.append(
                {
                    **common,
                    "change_type": "missing_payload_variant",
                    "payload_hex": payload_hex,
                    "baseline": baseline_variants[payload_hex],
                }
            )

    baseline_positions = {
        int(item["index"]): item for item in baseline["byte_positions"]
    }
    current_positions = {
        int(item["index"]): item for item in current["byte_positions"]
    }
    for index in sorted(baseline_positions.keys() | current_positions.keys()):
        baseline_position = baseline_positions.get(index)
        current_position = current_positions.get(index)
        change_type = _byte_change_type(baseline_position, current_position)
        if change_type is None:
            continue
        changes.append(
            {
                **common,
                "change_type": change_type,
                "byte_index": index,
                "baseline": baseline_position,
                "current": current_position,
            }
        )
    return changes


def _byte_change_type(
    baseline: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> str | None:
    if baseline is None and current is not None:
        return "byte_position_added"
    if baseline is not None and current is None:
        return "byte_position_removed"
    if baseline is None or current is None:
        return None

    baseline_values = {int(item["value"]) for item in baseline["values"]}
    current_values = {int(item["value"]) for item in current["values"]}
    baseline_constant = bool(baseline["is_constant"])
    current_constant = bool(current["is_constant"])
    if baseline_constant and current_constant:
        if baseline_values != current_values:
            return "constant_byte_changed"
    elif baseline_constant and not current_constant:
        return "byte_became_variable"
    elif not baseline_constant and current_constant:
        return "byte_became_constant"
    elif baseline_values != current_values:
        return "byte_value_set_changed"

    baseline_presence = float(baseline["presence_percent"])
    current_presence = float(current["presence_percent"])
    if baseline_presence != current_presence:
        return "byte_presence_changed"
    return None


def _comparison_input(context: AnalysisContext) -> tuple[Any, ComparisonContext]:
    if len(context.inputs) != 1 or context.inputs[0].kind != "comparison_set":
        raise ValueError("payload difference requires exactly one comparison_set input")
    comparison = context.comparison
    if comparison is None:
        raise ValueError("payload difference requires comparison context")
    if comparison.id != context.inputs[0].source_id:
        raise ValueError("comparison context does not match analysis input")
    return context.inputs[0], comparison


def _parameters(value: Any) -> dict[str, Any]:
    payload = dict(value or {})
    return {
        "maximum_variants_per_message_session": _integer_parameter(
            payload,
            "maximum_variants_per_message_session",
            _DEFAULT_MAXIMUM_VARIANTS_PER_MESSAGE_SESSION,
            1,
            _MAXIMUM_VARIANTS_LIMIT,
        ),
        "maximum_ranked_changes": _integer_parameter(
            payload,
            "maximum_ranked_changes",
            _DEFAULT_MAXIMUM_RANKED_CHANGES,
            1,
            _MAXIMUM_RANKED_CHANGES_LIMIT,
        ),
        "minimum_message_frame_count": _integer_parameter(
            payload,
            "minimum_message_frame_count",
            _DEFAULT_MINIMUM_MESSAGE_FRAME_COUNT,
            1,
            1_000_000_000,
        ),
    }


def _integer_parameter(
    payload: dict[str, Any],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = payload.get(key, default)
    message = f"{key} must be an integer between {minimum} and {maximum}"
    if isinstance(value, bool):
        raise ValueError(message)
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(message) from exc
    if isinstance(value, float) and (not isfinite(value) or not value.is_integer()):
        raise ValueError(message)
    if isinstance(value, str) and str(number) != value.strip():
        raise ValueError(message)
    if not minimum <= number <= maximum:
        raise ValueError(message)
    return number


def _message_key(frame: CanFrame) -> MessageKey:
    return (
        frame.channel,
        frame.arbitration_id,
        frame.is_extended_id,
        frame.is_remote_frame,
        frame.is_error_frame,
    )


def _message_key_payload(key: MessageKey) -> dict[str, Any]:
    channel, arbitration_id, extended, remote, error = key
    width = 8 if extended else 3
    kind = "error" if error else "remote" if remote else "data"
    return {
        "message_key": (
            f"{channel}:{'EXT' if extended else 'STD'}:"
            f"{arbitration_id:0{width}X}:{kind}"
        ),
        "channel": channel,
        "arbitration_id": arbitration_id,
        "arbitration_id_hex": f"{arbitration_id:0{width}X}",
        "is_extended_id": extended,
        "frame_kind": kind,
        "is_remote_frame": remote,
        "is_error_frame": error,
    }


def _message_key_sort(key: MessageKey) -> tuple[int, bool, int, bool, bool]:
    channel, arbitration_id, extended, remote, error = key
    return channel, extended, arbitration_id, error, remote


def _change_priority(change_type: str) -> int:
    priority = {
        "missing_message_key": 0,
        "new_message_key": 1,
        "dlc_set_changed": 2,
        "variant_comparison_truncated": 3,
        "constant_byte_changed": 4,
        "byte_became_variable": 5,
        "byte_became_constant": 6,
        "byte_value_set_changed": 7,
        "byte_position_removed": 8,
        "byte_position_added": 9,
        "missing_payload_variant": 10,
        "new_payload_variant": 11,
        "byte_presence_changed": 12,
    }
    return priority.get(change_type, 99)


def _round(value: float) -> float:
    return round(float(value), 6)


__all__ = [
    "PAYLOAD_DIFFERENCE_ALGORITHM_VERSION",
    "PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION",
    "PAYLOAD_DIFFERENCE_PROVIDER_ID",
    "PAYLOAD_DIFFERENCE_PROVIDER_VERSION",
    "PayloadDifferenceProvider",
]
