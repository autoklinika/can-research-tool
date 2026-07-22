from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from app.domain import Artifact, ArtifactSource
from app.models import CanFrame

from ..contracts import AnalysisContext, ComparisonContext, SessionSource
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType


COMPARISON_STATISTICS_PROVIDER_ID = "crt.comparison.statistics"
COMPARISON_STATISTICS_PROVIDER_VERSION = "1.0.0"
COMPARISON_STATISTICS_ALGORITHM_VERSION = "1"
COMPARISON_STATISTICS_ARTIFACT_SCHEMA_VERSION = 1
_PROGRESS_STRIDE = 4096
_DEFAULT_FREQUENCY_THRESHOLD_PERCENT = 10.0
_DEFAULT_SHARE_THRESHOLD_PERCENTAGE_POINTS = 0.5
_DEFAULT_MAXIMUM_RANKED_CHANGES = 250
_MAXIMUM_RANKED_CHANGES_LIMIT = 5000

MessageKey = tuple[int, int, bool, bool, bool]


@dataclass(slots=True)
class _MessageStats:
    count: int = 0
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    positive_interval_count: int = 0
    positive_interval_sum_ns: int = 0

    def add(self, timestamp_ns: int) -> None:
        if self.count == 0:
            self.first_timestamp_ns = timestamp_ns
        elif self.last_timestamp_ns is not None:
            delta = timestamp_ns - self.last_timestamp_ns
            if delta > 0:
                self.positive_interval_count += 1
                self.positive_interval_sum_ns += delta
        self.count += 1
        self.last_timestamp_ns = timestamp_ns

    def payload(self, total_frames: int) -> dict[str, Any]:
        mean_interval: float | None = None
        frequency: float | None = None
        if self.positive_interval_count:
            mean_interval = self.positive_interval_sum_ns / self.positive_interval_count
            frequency = 1_000_000_000.0 / mean_interval
        return {
            "frame_count": self.count,
            "share_percent": _round(0.0 if not total_frames else self.count * 100 / total_frames),
            "first_timestamp_ns": self.first_timestamp_ns,
            "last_timestamp_ns": self.last_timestamp_ns,
            "positive_interval_count": self.positive_interval_count,
            "mean_positive_interval_ns": None if mean_interval is None else _round(mean_interval),
            "mean_positive_frequency_hz": None if frequency is None else _round(frequency),
        }


@dataclass(slots=True)
class _SessionStats:
    source: SessionSource
    frame_count: int = 0
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    min_timestamp_ns: int | None = None
    max_timestamp_ns: int | None = None
    messages: dict[MessageKey, _MessageStats] = field(default_factory=dict)

    def add(self, frame: CanFrame) -> None:
        if self.frame_count == 0:
            self.first_timestamp_ns = frame.timestamp_ns
        self.frame_count += 1
        self.last_timestamp_ns = frame.timestamp_ns
        self.min_timestamp_ns = (
            frame.timestamp_ns
            if self.min_timestamp_ns is None
            else min(self.min_timestamp_ns, frame.timestamp_ns)
        )
        self.max_timestamp_ns = (
            frame.timestamp_ns
            if self.max_timestamp_ns is None
            else max(self.max_timestamp_ns, frame.timestamp_ns)
        )
        self.messages.setdefault(_message_key(frame), _MessageStats()).add(frame.timestamp_ns)

    def summary(self) -> dict[str, Any]:
        span = (
            None
            if self.min_timestamp_ns is None or self.max_timestamp_ns is None
            else self.max_timestamp_ns - self.min_timestamp_ns
        )
        arbitration_ids = {(key[1], key[2]) for key in self.messages}
        return {
            "id": self.source.id,
            "name": self.source.name,
            "source": self.source.source,
            "status": self.source.status,
            "declared_frame_count": self.source.frame_count,
            "reader_frame_count": self.source.frames.frame_count,
            "observed_frame_count": self.frame_count,
            "unique_arbitration_id_count": len(arbitration_ids),
            "unique_message_key_count": len(self.messages),
            "first_timestamp_ns": self.first_timestamp_ns,
            "last_timestamp_ns": self.last_timestamp_ns,
            "min_timestamp_ns": self.min_timestamp_ns,
            "max_timestamp_ns": self.max_timestamp_ns,
            "timestamp_span_ns": span,
            "timestamp_span_s": None if span is None else _round(span / 1e9),
            "sha256": self.source.sha256,
        }


class ComparisonStatisticsProvider:
    """Deterministic passive CAN-ID statistics comparison."""

    manifest = ExtensionManifest(
        id=COMPARISON_STATISTICS_PROVIDER_ID,
        name="CAN ID statistics comparison",
        version=COMPARISON_STATISTICS_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.COMPARISON,
        inputs=("comparison_set",),
        outputs=("comparison_statistics",),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.SESSION_READ,
            ExtensionPermission.ARTIFACT_WRITE,
        ),
    )
    algorithm_version = COMPARISON_STATISTICS_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input, comparison = _comparison_input(context)
        if comparison.synchronization_mode != "none":
            raise ValueError(
                "comparison statistics Stage 1 supports only synchronization_mode none"
            )
        parameters = _parameters(analysis_input.parameters)
        sources = tuple(
            context.project.session(session_id) for session_id in comparison.session_ids
        )
        total_work = sum(source.frames.frame_count for source in sources) + 1
        context.progress.report(0, total_work, "reading immutable comparison sessions")

        by_session: dict[str, _SessionStats] = {}
        processed = 0
        for source in sources:
            stats = _SessionStats(source)
            for frame in source.frames.iter_frames():
                context.cancellation.raise_if_cancelled()
                stats.add(frame)
                processed += 1
                if processed % _PROGRESS_STRIDE == 0:
                    context.progress.report(processed, total_work, f"analysed {processed} frames")
            by_session[source.id] = stats
            context.progress.report(processed, total_work, f"analysed session {source.name}")

        baseline_id = comparison.base_session_id or comparison.session_ids[0]
        baseline = by_session[baseline_id]
        ordered = tuple(by_session[session_id] for session_id in comparison.session_ids)
        keys = sorted(
            {key for session in ordered for key in session.messages},
            key=_message_key_sort,
        )
        sessions, comparisons = _summaries(ordered, baseline, parameters)
        matrix, notable, notable_count = _matrix(keys, ordered, baseline, parameters)
        payload = {
            "schema": "crt.comparison_statistics",
            "schema_version": COMPARISON_STATISTICS_ARTIFACT_SCHEMA_VERSION,
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
                "union_message_key_count": len(keys),
                "notable_change_count": notable_count,
                "returned_notable_change_count": len(notable),
                "notable_changes_truncated": notable_count > len(notable),
                "comparisons": comparisons,
            },
            "sessions": sessions,
            "message_keys": matrix,
            "notable_changes": notable,
        }
        sources_metadata = tuple(
            ArtifactSource(
                session_id=session.source.id,
                source_kind="session",
                source_reference={
                    "comparison_set_id": comparison.id,
                    "role": "base" if session.source.id == baseline_id else "compared",
                    "frame_count": session.frame_count,
                    "sha256": session.source.sha256,
                },
            )
            for session in ordered
        )
        artifact = context.artifact_writer.write_json(
            filename="comparison-statistics.json",
            artifact_type="comparison_statistics",
            schema_version=COMPARISON_STATISTICS_ARTIFACT_SCHEMA_VERSION,
            sources=sources_metadata,
            payload=payload,
            metadata={
                "comparison_set_id": comparison.id,
                "baseline_session_id": baseline_id,
                "session_count": len(ordered),
                "message_key_count": len(keys),
                "notable_change_count": notable_count,
            },
        )
        context.progress.report(total_work, total_work, "saved comparison statistics")
        return artifact


def _summaries(
    sessions: tuple[_SessionStats, ...],
    baseline: _SessionStats,
    parameters: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline_keys = set(baseline.messages)
    summaries: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    for session in sessions:
        is_base = session.source.id == baseline.source.id
        current_keys = set(session.messages)
        new_keys = current_keys - baseline_keys
        missing_keys = baseline_keys - current_keys
        common_keys = baseline_keys & current_keys
        counts = {
            "frequency_increase_count": 0,
            "frequency_decrease_count": 0,
            "share_increase_count": 0,
            "share_decrease_count": 0,
        }
        if not is_base:
            for key in common_keys:
                change = _change(
                    _metrics(baseline, key),
                    _metrics(session, key),
                    parameters,
                )
                for reason in change["reasons"]:
                    counter = f"{reason}_count"
                    if counter in counts:
                        counts[counter] += 1
        values = {
            **session.summary(),
            "role": "base" if is_base else "compared",
            "new_message_key_count": 0 if is_base else len(new_keys),
            "missing_message_key_count": 0 if is_base else len(missing_keys),
            "common_message_key_count": len(baseline_keys) if is_base else len(common_keys),
            **counts,
        }
        summaries.append(values)
        if not is_base:
            comparisons.append(
                {
                    "session_id": session.source.id,
                    "session_name": session.source.name,
                    "new_message_key_count": len(new_keys),
                    "missing_message_key_count": len(missing_keys),
                    "common_message_key_count": len(common_keys),
                    **counts,
                }
            )
    return summaries, comparisons


def _matrix(
    keys: list[MessageKey],
    sessions: tuple[_SessionStats, ...],
    baseline: _SessionStats,
    parameters: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    matrix: list[dict[str, Any]] = []
    notable: list[dict[str, Any]] = []
    order = {session.source.id: index for index, session in enumerate(sessions)}
    for key in keys:
        key_data = _message_key_payload(key)
        baseline_metrics = _metrics(baseline, key)
        session_rows = []
        for session in sessions:
            current = _metrics(session, key)
            change = _change(baseline_metrics, current, parameters)
            session_rows.append(
                {
                    "session_id": session.source.id,
                    "session_name": session.source.name,
                    "role": "base" if session.source.id == baseline.source.id else "compared",
                    "present": current is not None,
                    "statistics": current,
                    "change": change,
                }
            )
            if session.source.id != baseline.source.id and change["reasons"]:
                notable.append(
                    {
                        **key_data,
                        "session_id": session.source.id,
                        "session_name": session.source.name,
                        "reasons": list(change["reasons"]),
                        "baseline": baseline_metrics,
                        "current": current,
                        "frequency_delta_hz": change["frequency_delta_hz"],
                        "frequency_delta_percent": change["frequency_delta_percent"],
                        "share_delta_percentage_points": change[
                            "share_delta_percentage_points"
                        ],
                    }
                )
        matrix.append({**key_data, "baseline": baseline_metrics, "sessions": session_rows})
    notable.sort(
        key=lambda item: (
            order[str(item["session_id"])],
            _reason_priority(item["reasons"]),
            -_change_magnitude(item),
            int(item["channel"]),
            bool(item["is_extended_id"]),
            int(item["arbitration_id"]),
            str(item["frame_kind"]),
        )
    )
    count = len(notable)
    return matrix, notable[: parameters["maximum_ranked_changes"]], count


def _change(
    baseline: dict[str, Any] | None,
    current: dict[str, Any] | None,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    frequency_delta_hz: float | None = None
    frequency_delta_percent: float | None = None
    share_delta: float | None = None
    if baseline is None and current is not None:
        reasons.append("new")
    elif baseline is not None and current is None:
        reasons.append("missing")
    elif baseline is not None and current is not None:
        base_hz = baseline["mean_positive_frequency_hz"]
        current_hz = current["mean_positive_frequency_hz"]
        if base_hz is not None and current_hz is not None:
            frequency_delta_hz = _round(float(current_hz) - float(base_hz))
            frequency_delta_percent = _frequency_delta_percent(base_hz, current_hz)
            if (
                frequency_delta_percent is not None
                and abs(frequency_delta_percent)
                >= parameters["frequency_change_threshold_percent"]
            ):
                reasons.append(
                    "frequency_increase" if frequency_delta_percent > 0 else "frequency_decrease"
                )
        share_delta = _round(float(current["share_percent"]) - float(baseline["share_percent"]))
        if abs(share_delta) >= parameters["share_change_threshold_percentage_points"]:
            reasons.append("share_increase" if share_delta > 0 else "share_decrease")
    return {
        "reasons": reasons,
        "frequency_delta_hz": frequency_delta_hz,
        "frequency_delta_percent": frequency_delta_percent,
        "share_delta_percentage_points": share_delta,
    }


def _metrics(session: _SessionStats, key: MessageKey) -> dict[str, Any] | None:
    message = session.messages.get(key)
    return None if message is None else message.payload(session.frame_count)


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


def _comparison_input(context: AnalysisContext) -> tuple[Any, ComparisonContext]:
    if len(context.inputs) != 1 or context.inputs[0].kind != "comparison_set":
        raise ValueError("comparison statistics requires exactly one comparison_set input")
    comparison = context.comparison
    if comparison is None:
        raise ValueError("comparison statistics requires comparison context")
    if comparison.id != context.inputs[0].source_id:
        raise ValueError("comparison context does not match analysis input")
    return context.inputs[0], comparison


def _parameters(value: Any) -> dict[str, Any]:
    payload = dict(value or {})
    return {
        "frequency_change_threshold_percent": _number_parameter(
            payload,
            "frequency_change_threshold_percent",
            _DEFAULT_FREQUENCY_THRESHOLD_PERCENT,
        ),
        "share_change_threshold_percentage_points": _number_parameter(
            payload,
            "share_change_threshold_percentage_points",
            _DEFAULT_SHARE_THRESHOLD_PERCENTAGE_POINTS,
        ),
        "maximum_ranked_changes": _integer_parameter(
            payload,
            "maximum_ranked_changes",
            _DEFAULT_MAXIMUM_RANKED_CHANGES,
        ),
    }


def _number_parameter(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a finite non-negative number") from exc
    if not isfinite(number) or number < 0:
        raise ValueError(f"{key} must be a finite non-negative number")
    return _round(number)


def _integer_parameter(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    message = f"{key} must be an integer between 1 and {_MAXIMUM_RANKED_CHANGES_LIMIT}"
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
    if not 1 <= number <= _MAXIMUM_RANKED_CHANGES_LIMIT:
        raise ValueError(message)
    return number


def _frequency_delta_percent(baseline: Any, current: Any) -> float | None:
    baseline_value = float(baseline)
    if baseline_value == 0.0:
        return None
    return _round((float(current) - baseline_value) * 100 / baseline_value)


def _reason_priority(reasons: Any) -> int:
    priority = {
        "missing": 0,
        "new": 1,
        "frequency_decrease": 2,
        "frequency_increase": 3,
        "share_decrease": 4,
        "share_increase": 5,
    }
    return min((priority.get(str(reason), 99) for reason in reasons), default=99)


def _change_magnitude(item: dict[str, Any]) -> float:
    values = (item.get("frequency_delta_percent"), item.get("share_delta_percentage_points"))
    return max((abs(float(value)) for value in values if value is not None), default=0.0)


def _round(value: float) -> float:
    return round(float(value), 6)


__all__ = [
    "COMPARISON_STATISTICS_ALGORITHM_VERSION",
    "COMPARISON_STATISTICS_ARTIFACT_SCHEMA_VERSION",
    "COMPARISON_STATISTICS_PROVIDER_ID",
    "COMPARISON_STATISTICS_PROVIDER_VERSION",
    "ComparisonStatisticsProvider",
]
