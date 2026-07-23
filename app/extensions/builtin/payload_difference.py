from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from app.domain import Artifact, ArtifactSource
from app.models import CanFrame

from ..contracts import AnalysisContext, ComparisonContext, SessionSource
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType


PAYLOAD_DIFFERENCE_PROVIDER_ID = "crt.comparison.payload_differences"
PAYLOAD_DIFFERENCE_PROVIDER_VERSION = "1.0.0"
PAYLOAD_DIFFERENCE_ALGORITHM_VERSION = "1"
PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION = 1

_PROGRESS_STRIDE = 4096
_DEFAULT_MAX_VARIANTS_PER_MESSAGE = 1000
_DEFAULT_MAX_RANKED_CHANGES = 500
_DEFAULT_DOMINANT_SHARE_DELTA_THRESHOLD_PP = 5.0
_DEFAULT_MINIMUM_MESSAGE_FRAME_COUNT = 1
_MAX_VARIANTS_LIMIT = 100_000
_MAX_RANKED_CHANGES_LIMIT = 5000

MessageKey = tuple[int, int, bool, bool, bool]


@dataclass(slots=True)
class _VariantStats:
    count: int = 0
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None

    def add(self, timestamp_ns: int) -> None:
        if self.count == 0:
            self.first_timestamp_ns = timestamp_ns
        self.count += 1
        self.last_timestamp_ns = timestamp_ns

    def payload(self, data: bytes, frame_count: int) -> dict[str, Any]:
        return {
            "payload_hex": data.hex(" ").upper(),
            "dlc": len(data),
            "count": self.count,
            "share_percent": _round(self.count * 100 / frame_count),
            "first_timestamp_ns": self.first_timestamp_ns,
            "last_timestamp_ns": self.last_timestamp_ns,
        }


@dataclass(slots=True)
class _ByteStats:
    observed_count: int = 0
    values: Counter[int] = field(default_factory=Counter)

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
            for value, count in sorted(self.values.items())
        ]
        dominant_value: int | None = None
        dominant_count = 0
        if observed:
            dominant = min(
                observed,
                key=lambda item: (-int(item["count"]), int(item["value"])),
            )
            dominant_value = int(dominant["value"])
            dominant_count = int(dominant["count"])
        return {
            "observed_count": self.observed_count,
            "presence_percent": _round(
                0.0 if not frame_count else self.observed_count * 100 / frame_count
            ),
            "classification": (
                "absent"
                if not observed
                else "constant"
                if len(observed) == 1
                else "variable"
            ),
            "unique_value_count": len(observed),
            "minimum_value": None if not observed else int(observed[0]["value"]),
            "minimum_value_hex": None if not observed else str(observed[0]["value_hex"]),
            "maximum_value": None if not observed else int(observed[-1]["value"]),
            "maximum_value_hex": None if not observed else str(observed[-1]["value_hex"]),
            "dominant_value": dominant_value,
            "dominant_value_hex": (
                None if dominant_value is None else f"{dominant_value:02X}"
            ),
            "dominant_count": dominant_count,
            "dominant_share_percent": _round(
                0.0
                if not self.observed_count
                else dominant_count * 100 / self.observed_count
            ),
            "values": observed,
        }


@dataclass(slots=True)
class _MessagePayloadStats:
    frame_count: int = 0
    dlc_counts: Counter[int] = field(default_factory=Counter)
    tracked_variants: dict[bytes, _VariantStats] = field(default_factory=dict)
    untracked_variant_frame_count: int = 0
    byte_positions: list[_ByteStats] = field(default_factory=list)

    def add(
        self,
        frame: CanFrame,
        max_variants_per_message: int,
    ) -> None:
        self.frame_count += 1
        self.dlc_counts[len(frame.data)] += 1
        data = bytes(frame.data)
        variant = self.tracked_variants.get(data)
        if variant is not None:
            variant.add(frame.timestamp_ns)
        elif len(self.tracked_variants) < max_variants_per_message:
            variant = _VariantStats()
            variant.add(frame.timestamp_ns)
            self.tracked_variants[data] = variant
        else:
            self.untracked_variant_frame_count += 1
        while len(self.byte_positions) < len(data):
            self.byte_positions.append(_ByteStats())
        for index, value in enumerate(data):
            self.byte_positions[index].add(value)

    def payload(self) -> dict[str, Any]:
        variants = sorted(
            (
                stats.payload(data, self.frame_count)
                for data, stats in self.tracked_variants.items()
            ),
            key=lambda item: (
                -int(item["count"]),
                int(item["dlc"]),
                str(item["payload_hex"]),
            ),
        )
        byte_positions = [
            {"index": index, **stats.payload(self.frame_count)}
            for index, stats in enumerate(self.byte_positions)
        ]
        return {
            "frame_count": self.frame_count,
            "dlc_counts": [
                {
                    "dlc": dlc,
                    "count": count,
                    "share_percent": _round(count * 100 / self.frame_count),
                }
                for dlc, count in sorted(self.dlc_counts.items())
            ],
            "variant_tracking": {
                "configured_limit": None,
                "selection_rule": "first_observed_in_session_order",
                "tracked_variant_count": len(variants),
                "tracked_variant_frame_count": sum(
                    int(item["count"]) for item in variants
                ),
                "untracked_variant_frame_count": self.untracked_variant_frame_count,
                "complete": self.untracked_variant_frame_count == 0,
            },
            "variants": variants,
            "byte_position_count": len(byte_positions),
            "constant_byte_position_count": sum(
                1
                for item in byte_positions
                if item["classification"] == "constant"
            ),
            "variable_byte_position_count": sum(
                1
                for item in byte_positions
                if item["classification"] == "variable"
            ),
            "byte_positions": byte_positions,
        }


@dataclass(slots=True)
class _SessionPayloadStats:
    source: SessionSource
    data_frame_count: int = 0
    skipped_non_data_frame_count: int = 0
    messages: dict[MessageKey, _MessagePayloadStats] = field(default_factory=dict)

    def add(
        self,
        frame: CanFrame,
        max_variants_per_message: int,
    ) -> None:
        if frame.is_remote_frame or frame.is_error_frame:
            self.skipped_non_data_frame_count += 1
            return
        self.data_frame_count += 1
        message = self.messages.setdefault(
            _message_key(frame),
            _MessagePayloadStats(),
        )
        message.add(frame, max_variants_per_message)

    def summary(
        self,
        baseline_keys: set[MessageKey],
        baseline_id: str,
    ) -> dict[str, Any]:
        own_keys = set(self.messages)
        is_base = self.source.id == baseline_id
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
            "new_payload_message_key_count": (
                0 if is_base else len(own_keys - baseline_keys)
            ),
            "missing_payload_message_key_count": (
                0 if is_base else len(baseline_keys - own_keys)
            ),
            "tracked_payload_variant_count": sum(
                len(message.tracked_variants)
                for message in self.messages.values()
            ),
            "untracked_payload_variant_frame_count": sum(
                message.untracked_variant_frame_count
                for message in self.messages.values()
            ),
            "constant_byte_position_count": sum(
                sum(
                    1
                    for byte in message.byte_positions
                    if len(byte.values) == 1
                )
                for message in self.messages.values()
            ),
            "variable_byte_position_count": sum(
                sum(
                    1
                    for byte in message.byte_positions
                    if len(byte.values) > 1
                )
                for message in self.messages.values()
            ),
            "sha256": self.source.sha256,
        }


class PayloadDifferenceProvider:
    """Deterministic passive comparison of CAN payload variants and bytes."""

    manifest = ExtensionManifest(
        id=PAYLOAD_DIFFERENCE_PROVIDER_ID,
        name="CAN payload differences",
        version=PAYLOAD_DIFFERENCE_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.COMPARISON,
        inputs=("comparison_set",),
        outputs=("payload_differences",),
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
                "payload differences Stage 2 support only synchronization_mode none"
            )
        parameters = _parameters(analysis_input.parameters)
        sources = tuple(
            context.project.session(session_id)
            for session_id in comparison.session_ids
        )
        total_work = sum(source.frames.frame_count for source in sources) + 1
        context.progress.report(
            0,
            total_work,
            "reading immutable payload sessions",
        )

        by_session: dict[str, _SessionPayloadStats] = {}
        processed = 0
        for source in sources:
            stats = _SessionPayloadStats(source)
            for frame in source.frames.iter_frames():
                context.cancellation.raise_if_cancelled()
                stats.add(
                    frame,
                    parameters["max_variants_per_message"],
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

        baseline_id = (
            comparison.base_session_id
            or comparison.session_ids[0]
        )
        baseline = by_session[baseline_id]
        ordered = tuple(
            by_session[session_id]
            for session_id in comparison.session_ids
        )
        keys = sorted(
            {
                key
                for session in ordered
                for key in session.messages
            },
            key=_message_key_sort,
        )
        baseline_keys = set(baseline.messages)
        sessions = [
            session.summary(baseline_keys, baseline_id)
            for session in ordered
        ]
        (
            message_keys,
            notable,
            notable_count,
            change_counts,
        ) = _message_matrix(
            keys,
            ordered,
            baseline,
            parameters,
        )
        variant_tracking_complete = all(
            not message.untracked_variant_frame_count
            for session in ordered
            for message in session.messages.values()
        )
        payload = {
            "schema": "crt.payload_differences",
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
                    set.intersection(
                        *(set(session.messages) for session in ordered)
                    )
                ),
                "tracked_payload_variant_count": sum(
                    len(message.tracked_variants)
                    for session in ordered
                    for message in session.messages.values()
                ),
                "constant_byte_change_count": change_counts[
                    "constant_byte_changed"
                ],
                "constant_variable_transition_count": (
                    change_counts["byte_became_variable"]
                    + change_counts["byte_became_constant"]
                ),
                "byte_value_set_change_count": change_counts[
                    "byte_value_set_changed"
                ],
                "notable_change_count": notable_count,
                "returned_notable_change_count": len(notable),
                "notable_changes_truncated": notable_count > len(notable),
                "change_type_counts": [
                    {"change_type": key, "count": count}
                    for key, count in sorted(change_counts.items())
                ],
            },
            "sessions": sessions,
            "message_payload_profiles": message_keys,
            "ranked_changes": notable,
            "truncation": {
                "variant_tracking_complete": variant_tracking_complete,
                "selection_rule": "first_observed_in_session_order",
                "messages_with_truncated_variants": sum(
                    1
                    for session in ordered
                    for message in session.messages.values()
                    if message.untracked_variant_frame_count
                ),
                "untracked_variant_frame_count": sum(
                    message.untracked_variant_frame_count
                    for session in ordered
                    for message in session.messages.values()
                ),
            },
        }
        artifact_sources = tuple(
            ArtifactSource(
                session_id=session.source.id,
                source_kind="session",
                source_reference={
                    "comparison_set_id": comparison.id,
                    "role": (
                        "base"
                        if session.source.id == baseline_id
                        else "comparison"
                    ),
                    "position": index,
                    "frame_count": session.source.frames.frame_count,
                    "data_frame_count": session.data_frame_count,
                    "sha256": session.source.sha256,
                },
            )
            for index, session in enumerate(ordered)
        )
        artifact = context.artifact_writer.write_json(
            filename="payload-differences.json",
            artifact_type="payload_differences",
            schema_version=PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION,
            sources=artifact_sources,
            payload=payload,
            metadata={
                "comparison_set_id": comparison.id,
                "baseline_session_id": baseline_id,
                "session_count": len(ordered),
                "payload_message_key_count": len(keys),
                "notable_change_count": notable_count,
                "variant_tracking_complete": variant_tracking_complete,
            },
        )
        context.progress.report(
            total_work,
            total_work,
            "saved payload differences",
        )
        return artifact


def _message_matrix(
    keys: list[MessageKey],
    sessions: tuple[_SessionPayloadStats, ...],
    baseline: _SessionPayloadStats,
    parameters: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    int,
    Counter[str],
]:
    matrix: list[dict[str, Any]] = []
    notable: list[dict[str, Any]] = []
    change_counts: Counter[str] = Counter()
    session_order = {
        session.source.id: index
        for index, session in enumerate(sessions)
    }
    for key in keys:
        key_payload = _message_key_payload(key)
        full_profiles = {
            session.source.id: (
                session.messages[key].payload()
                if key in session.messages
                else None
            )
            for session in sessions
        }
        baseline_profile = full_profiles[baseline.source.id]
        variant_matrix, variant_matrix_complete = _variant_matrix(
            sessions,
            full_profiles,
            baseline.source.id,
        )
        session_rows: list[dict[str, Any]] = []
        for session in sessions:
            current_profile = full_profiles[session.source.id]
            changes = _compare_message(
                key_payload,
                baseline.source.id,
                session,
                baseline_profile,
                current_profile,
                parameters,
            )
            for change in changes:
                change_counts[str(change["change_type"])] += 1
            session_rows.append(
                {
                    "session_id": session.source.id,
                    "session_name": session.source.name,
                    "role": (
                        "base"
                        if session.source.id == baseline.source.id
                        else "compared"
                    ),
                    "present": current_profile is not None,
                    "payload_profile": _public_message_profile(
                        current_profile,
                        parameters["include_byte_histograms"],
                        parameters["max_variants_per_message"],
                    ),
                    "comparison_to_baseline": changes,
                    "change_count": len(changes),
                }
            )
            notable.extend(changes)
        matrix.append(
            {
                **key_payload,
                "baseline": _public_message_profile(
                    baseline_profile,
                    parameters["include_byte_histograms"],
                    parameters["max_variants_per_message"],
                ),
                "sessions": session_rows,
                "variant_matrix_complete": variant_matrix_complete,
                "variant_matrix": (
                    variant_matrix
                    if parameters["include_complete_variant_matrix"]
                    else []
                ),
            }
        )
    notable.sort(
        key=lambda item: (
            session_order[str(item["session_id"])],
            _change_priority(str(item["change_type"])),
            int(item["channel"]),
            bool(item["is_extended_id"]),
            int(item["arbitration_id"]),
            bool(item["is_error_frame"]),
            bool(item["is_remote_frame"]),
            int(item.get("byte_index", -1)),
            int(item.get("dlc", -1)),
            str(item.get("payload_hex", "")),
        )
    )
    count = len(notable)
    return (
        matrix,
        notable[: parameters["max_ranked_changes"]],
        count,
        change_counts,
    )


def _variant_matrix(
    sessions: tuple[_SessionPayloadStats, ...],
    profiles: dict[str, dict[str, Any] | None],
    baseline_id: str,
) -> tuple[list[dict[str, Any]], bool]:
    complete = all(
        profile is None
        or bool(profile["variant_tracking"]["complete"])
        for profile in profiles.values()
    )
    tracked: dict[str, dict[str, Any]] = {}
    for profile in profiles.values():
        if profile is None:
            continue
        for variant in profile["variants"]:
            tracked.setdefault(str(variant["payload_hex"]), variant)
    matrix: list[dict[str, Any]] = []
    for payload_hex in sorted(
        tracked,
        key=lambda value: (
            int(tracked[value]["dlc"]),
            value,
        ),
    ):
        rows = []
        present_ids: list[str] = []
        for session in sessions:
            profile = profiles[session.source.id]
            variant = None
            if profile is not None:
                variant = next(
                    (
                        item
                        for item in profile["variants"]
                        if item["payload_hex"] == payload_hex
                    ),
                    None,
                )
            if variant is not None:
                present_ids.append(session.source.id)
            rows.append(
                {
                    "session_id": session.source.id,
                    "session_name": session.source.name,
                    "present": variant is not None,
                    "statistics": variant,
                }
            )
        if not complete:
            role = "incomplete"
        elif len(present_ids) == len(sessions):
            role = "common"
        elif present_ids == [baseline_id]:
            role = "baseline_only"
        elif baseline_id not in present_ids and len(present_ids) == 1:
            role = "comparison_only"
        else:
            role = "subset_only"
        matrix.append(
            {
                "payload_hex": payload_hex,
                "dlc": int(tracked[payload_hex]["dlc"]),
                "role": role,
                "present_session_ids": present_ids,
                "missing_session_ids": [
                    session.source.id
                    for session in sessions
                    if session.source.id not in present_ids
                ],
                "sessions": rows,
            }
        )
    return matrix, complete


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
        int(baseline["frame_count"])
        < parameters["minimum_message_frame_count"]
        or int(current["frame_count"])
        < parameters["minimum_message_frame_count"]
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

    if (
        not baseline["variant_tracking"]["complete"]
        or not current["variant_tracking"]["complete"]
    ):
        changes.append(
            {
                **common,
                "change_type": "variant_comparison_truncated",
                "baseline_untracked_frame_count": baseline[
                    "variant_tracking"
                ]["untracked_variant_frame_count"],
                "current_untracked_frame_count": current[
                    "variant_tracking"
                ]["untracked_variant_frame_count"],
            }
        )
    else:
        baseline_variants = {
            str(item["payload_hex"]): item
            for item in baseline["variants"]
        }
        current_variants = {
            str(item["payload_hex"]): item
            for item in current["variants"]
        }
        for payload_hex in sorted(
            current_variants.keys() - baseline_variants.keys()
        ):
            item = current_variants[payload_hex]
            changes.append(
                {
                    **common,
                    "change_type": "new_payload_variant",
                    "payload_hex": payload_hex,
                    "dlc": item["dlc"],
                    "current": item,
                }
            )
        for payload_hex in sorted(
            baseline_variants.keys() - current_variants.keys()
        ):
            item = baseline_variants[payload_hex]
            changes.append(
                {
                    **common,
                    "change_type": "missing_payload_variant",
                    "payload_hex": payload_hex,
                    "dlc": item["dlc"],
                    "baseline": item,
                }
            )

    baseline_positions = {
        int(item["index"]): item
        for item in baseline["byte_positions"]
    }
    current_positions = {
        int(item["index"]): item
        for item in current["byte_positions"]
    }
    for index in sorted(
        baseline_positions.keys() | current_positions.keys()
    ):
        baseline_position = baseline_positions.get(index)
        current_position = current_positions.get(index)
        byte_changes = _byte_changes(
            baseline_position,
            current_position,
            parameters,
        )
        for change in byte_changes:
            changes.append(
                {
                    **common,
                    **change,
                    "byte_index": index,
                    "baseline": (
                        None
                        if baseline_position is None
                        else _public_byte_profile(
                            baseline_position,
                            parameters["include_byte_histograms"],
                        )
                    ),
                    "current": (
                        None
                        if current_position is None
                        else _public_byte_profile(
                            current_position,
                            parameters["include_byte_histograms"],
                        )
                    ),
                }
            )
    return changes


def _byte_changes(
    baseline: dict[str, Any] | None,
    current: dict[str, Any] | None,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    if baseline is None and current is not None:
        return [{"change_type": "byte_position_added"}]
    if baseline is not None and current is None:
        return [{"change_type": "byte_position_removed"}]
    if baseline is None or current is None:
        return []

    changes: list[dict[str, Any]] = []
    baseline_class = str(baseline["classification"])
    current_class = str(current["classification"])
    baseline_values = {
        int(item["value"])
        for item in baseline["values"]
    }
    current_values = {
        int(item["value"])
        for item in current["values"]
    }
    if baseline_class == "constant" and current_class == "constant":
        if baseline_values != current_values:
            changes.append({"change_type": "constant_byte_changed"})
    elif baseline_class == "constant" and current_class == "variable":
        changes.append({"change_type": "byte_became_variable"})
    elif baseline_class == "variable" and current_class == "constant":
        changes.append({"change_type": "byte_became_constant"})
    elif baseline_values != current_values:
        changes.append(
            {
                "change_type": "byte_value_set_changed",
                "new_values": sorted(current_values - baseline_values),
                "missing_values": sorted(baseline_values - current_values),
            }
        )

    if baseline["dominant_value"] != current["dominant_value"]:
        changes.append(
            {
                "change_type": "dominant_value_changed",
                "baseline_dominant_value": baseline["dominant_value"],
                "current_dominant_value": current["dominant_value"],
            }
        )
    dominant_share_delta = _round(
        float(current["dominant_share_percent"])
        - float(baseline["dominant_share_percent"])
    )
    if (
        abs(dominant_share_delta)
        >= parameters["dominant_share_delta_threshold_pp"]
    ):
        changes.append(
            {
                "change_type": "dominant_share_changed",
                "dominant_share_delta_percentage_points": dominant_share_delta,
            }
        )
    if baseline["presence_percent"] != current["presence_percent"]:
        changes.append(
            {
                "change_type": "byte_presence_changed",
                "presence_delta_percentage_points": _round(
                    float(current["presence_percent"])
                    - float(baseline["presence_percent"])
                ),
            }
        )
    return changes


def _public_message_profile(
    profile: dict[str, Any] | None,
    include_histograms: bool,
    configured_limit: int,
) -> dict[str, Any] | None:
    if profile is None:
        return None
    public = {
        **profile,
        "variant_tracking": {
            **profile["variant_tracking"],
            "configured_limit": configured_limit,
        },
        "byte_positions": [
            {
                **item,
                **(
                    {}
                    if include_histograms
                    else {"values": []}
                ),
            }
            for item in profile["byte_positions"]
        ],
    }
    return public


def _public_byte_profile(
    profile: dict[str, Any],
    include_histograms: bool,
) -> dict[str, Any]:
    return {
        **profile,
        **({} if include_histograms else {"values": []}),
    }


def _comparison_input(
    context: AnalysisContext,
) -> tuple[Any, ComparisonContext]:
    if (
        len(context.inputs) != 1
        or context.inputs[0].kind != "comparison_set"
    ):
        raise ValueError(
            "payload differences require exactly one comparison_set input"
        )
    comparison = context.comparison
    if comparison is None:
        raise ValueError("payload differences require comparison context")
    if comparison.id != context.inputs[0].source_id:
        raise ValueError("comparison context does not match analysis input")
    return context.inputs[0], comparison


def _parameters(value: Any) -> dict[str, Any]:
    payload = dict(value or {})
    return {
        "max_ranked_changes": _integer_parameter(
            payload,
            "max_ranked_changes",
            _DEFAULT_MAX_RANKED_CHANGES,
            1,
            _MAX_RANKED_CHANGES_LIMIT,
        ),
        "max_variants_per_message": _integer_parameter(
            payload,
            "max_variants_per_message",
            _DEFAULT_MAX_VARIANTS_PER_MESSAGE,
            1,
            _MAX_VARIANTS_LIMIT,
        ),
        "dominant_share_delta_threshold_pp": _number_parameter(
            payload,
            "dominant_share_delta_threshold_pp",
            _DEFAULT_DOMINANT_SHARE_DELTA_THRESHOLD_PP,
        ),
        "include_complete_variant_matrix": _boolean_parameter(
            payload,
            "include_complete_variant_matrix",
            True,
        ),
        "include_byte_histograms": _boolean_parameter(
            payload,
            "include_byte_histograms",
            True,
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
    if (
        isinstance(value, float)
        and (not isfinite(value) or not value.is_integer())
    ):
        raise ValueError(message)
    if isinstance(value, str) and str(number) != value.strip():
        raise ValueError(message)
    if not minimum <= number <= maximum:
        raise ValueError(message)
    return number


def _number_parameter(
    payload: dict[str, Any],
    key: str,
    default: float,
) -> float:
    value = payload.get(key, default)
    message = f"{key} must be a finite non-negative number"
    if isinstance(value, bool):
        raise ValueError(message)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not isfinite(number) or number < 0:
        raise ValueError(message)
    return _round(number)


def _boolean_parameter(
    payload: dict[str, Any],
    key: str,
    default: bool,
) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


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


def _message_key_sort(
    key: MessageKey,
) -> tuple[int, bool, int, bool, bool]:
    channel, arbitration_id, extended, remote, error = key
    return channel, extended, arbitration_id, error, remote


def _change_priority(change_type: str) -> int:
    priority = {
        "new_payload_variant": 0,
        "missing_payload_variant": 1,
        "new_message_key": 2,
        "missing_message_key": 3,
        "constant_byte_changed": 4,
        "byte_became_variable": 5,
        "byte_became_constant": 6,
        "byte_value_set_changed": 7,
        "dominant_value_changed": 8,
        "dominant_share_changed": 9,
        "dlc_set_changed": 10,
        "byte_position_removed": 11,
        "byte_position_added": 12,
        "byte_presence_changed": 13,
        "variant_comparison_truncated": 14,
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
