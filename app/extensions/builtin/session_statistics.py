from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

from app.domain import Artifact, ArtifactSource
from app.models import CanFrame

from ..contracts import AnalysisContext
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType


SESSION_STATISTICS_PROVIDER_ID = "crt.analysis.session_statistics"
SESSION_STATISTICS_PROVIDER_VERSION = "1.0.0"
SESSION_STATISTICS_ALGORITHM_VERSION = "1"
SESSION_STATISTICS_ARTIFACT_SCHEMA_VERSION = 1
_PROGRESS_STRIDE = 4096


@dataclass(slots=True)
class _IntervalStatistics:
    last_timestamp_ns: int | None = None
    interval_count: int = 0
    positive_interval_count: int = 0
    zero_interval_count: int = 0
    negative_interval_count: int = 0
    positive_sum_ns: int = 0
    positive_sum_squares_ns: int = 0
    min_positive_ns: int | None = None
    max_positive_ns: int | None = None

    def add(self, timestamp_ns: int) -> None:
        if self.last_timestamp_ns is not None:
            delta = timestamp_ns - self.last_timestamp_ns
            self.interval_count += 1
            if delta > 0:
                self.positive_interval_count += 1
                self.positive_sum_ns += delta
                self.positive_sum_squares_ns += delta * delta
                self.min_positive_ns = (
                    delta if self.min_positive_ns is None else min(self.min_positive_ns, delta)
                )
                self.max_positive_ns = (
                    delta if self.max_positive_ns is None else max(self.max_positive_ns, delta)
                )
            elif delta == 0:
                self.zero_interval_count += 1
            else:
                self.negative_interval_count += 1
        self.last_timestamp_ns = timestamp_ns

    def to_payload(self) -> dict[str, Any]:
        mean_ns: float | None = None
        stddev_ns: float | None = None
        frequency_hz: float | None = None
        if self.positive_interval_count:
            mean = self.positive_sum_ns / self.positive_interval_count
            variance = (
                self.positive_sum_squares_ns / self.positive_interval_count
            ) - (mean * mean)
            mean_ns = _rounded(mean)
            stddev_ns = _rounded(sqrt(max(0.0, variance)))
            frequency_hz = _rounded(1_000_000_000.0 / mean)
        return {
            "interval_count": self.interval_count,
            "positive_interval_count": self.positive_interval_count,
            "zero_interval_count": self.zero_interval_count,
            "negative_interval_count": self.negative_interval_count,
            "min_positive_interval_ns": self.min_positive_ns,
            "max_positive_interval_ns": self.max_positive_ns,
            "mean_positive_interval_ns": mean_ns,
            "population_stddev_positive_interval_ns": stddev_ns,
            "mean_positive_frequency_hz": frequency_hz,
        }


@dataclass(slots=True)
class _MessageStatistics:
    channel: int
    arbitration_id: int
    is_extended_id: bool
    is_remote_frame: bool
    is_error_frame: bool
    frame_count: int = 0
    payload_bytes: int = 0
    first_source_row: int | None = None
    last_source_row: int | None = None
    first_sequence: int | None = None
    last_sequence: int | None = None
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    min_dlc: int | None = None
    max_dlc: int | None = None
    dlc_counts: dict[int, int] = field(default_factory=dict)
    timing: _IntervalStatistics = field(default_factory=_IntervalStatistics)

    def add(self, source_row: int, frame: CanFrame) -> None:
        if self.frame_count == 0:
            self.first_source_row = source_row
            self.first_sequence = frame.sequence
            self.first_timestamp_ns = frame.timestamp_ns
        self.frame_count += 1
        self.payload_bytes += frame.dlc
        self.last_source_row = source_row
        self.last_sequence = frame.sequence
        self.last_timestamp_ns = frame.timestamp_ns
        self.min_dlc = frame.dlc if self.min_dlc is None else min(self.min_dlc, frame.dlc)
        self.max_dlc = frame.dlc if self.max_dlc is None else max(self.max_dlc, frame.dlc)
        self.dlc_counts[frame.dlc] = self.dlc_counts.get(frame.dlc, 0) + 1
        self.timing.add(frame.timestamp_ns)

    def to_payload(self) -> dict[str, Any]:
        width = 8 if self.is_extended_id else 3
        return {
            "channel": self.channel,
            "arbitration_id": self.arbitration_id,
            "arbitration_id_hex": f"{self.arbitration_id:0{width}X}",
            "is_extended_id": self.is_extended_id,
            "frame_kind": _frame_kind(self.is_remote_frame, self.is_error_frame),
            "is_remote_frame": self.is_remote_frame,
            "is_error_frame": self.is_error_frame,
            "frame_count": self.frame_count,
            "payload_bytes": self.payload_bytes,
            "first_source_row": self.first_source_row,
            "last_source_row": self.last_source_row,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "first_timestamp_ns": self.first_timestamp_ns,
            "last_timestamp_ns": self.last_timestamp_ns,
            "min_dlc": self.min_dlc,
            "max_dlc": self.max_dlc,
            "dlc_distribution": _distribution(self.dlc_counts, "dlc"),
            "timing": self.timing.to_payload(),
        }


class SessionStatisticsProvider:
    """Deterministic passive statistics for one immutable raw-frame session."""

    manifest = ExtensionManifest(
        id=SESSION_STATISTICS_PROVIDER_ID,
        name="Session statistics",
        version=SESSION_STATISTICS_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.ANALYSIS,
        inputs=("session",),
        outputs=("session_statistics",),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.SESSION_READ,
            ExtensionPermission.ARTIFACT_WRITE,
        ),
    )

    algorithm_version = SESSION_STATISTICS_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input = _single_session_input(context)
        source = context.project.session(analysis_input.source_id)
        expected_frames = source.frames.frame_count
        progress_total = expected_frames + 1
        context.progress.report(0, progress_total, "reading immutable session")

        messages: dict[tuple[int, int, bool, bool, bool], _MessageStatistics] = {}
        channel_counts: dict[int, int] = {}
        dlc_counts: dict[int, int] = {}
        arbitration_ids: set[tuple[int, bool]] = set()
        capture_timing = _IntervalStatistics()

        observed_frames = 0
        payload_bytes = 0
        standard_frames = 0
        extended_frames = 0
        data_frames = 0
        remote_frames = 0
        error_frames = 0
        first_sequence: int | None = None
        last_sequence: int | None = None
        first_timestamp_ns: int | None = None
        last_timestamp_ns: int | None = None
        min_timestamp_ns: int | None = None
        max_timestamp_ns: int | None = None

        for source_row, frame in enumerate(source.frames.iter_frames()):
            context.cancellation.raise_if_cancelled()
            if observed_frames == 0:
                first_sequence = frame.sequence
                first_timestamp_ns = frame.timestamp_ns
            observed_frames += 1
            last_sequence = frame.sequence
            last_timestamp_ns = frame.timestamp_ns
            min_timestamp_ns = (
                frame.timestamp_ns
                if min_timestamp_ns is None
                else min(min_timestamp_ns, frame.timestamp_ns)
            )
            max_timestamp_ns = (
                frame.timestamp_ns
                if max_timestamp_ns is None
                else max(max_timestamp_ns, frame.timestamp_ns)
            )
            payload_bytes += frame.dlc
            channel_counts[frame.channel] = channel_counts.get(frame.channel, 0) + 1
            dlc_counts[frame.dlc] = dlc_counts.get(frame.dlc, 0) + 1
            arbitration_ids.add((frame.arbitration_id, frame.is_extended_id))
            capture_timing.add(frame.timestamp_ns)

            if frame.is_extended_id:
                extended_frames += 1
            else:
                standard_frames += 1
            if frame.is_error_frame:
                error_frames += 1
            elif frame.is_remote_frame:
                remote_frames += 1
            else:
                data_frames += 1

            key = (
                frame.channel,
                frame.arbitration_id,
                frame.is_extended_id,
                frame.is_remote_frame,
                frame.is_error_frame,
            )
            message = messages.get(key)
            if message is None:
                message = _MessageStatistics(
                    channel=frame.channel,
                    arbitration_id=frame.arbitration_id,
                    is_extended_id=frame.is_extended_id,
                    is_remote_frame=frame.is_remote_frame,
                    is_error_frame=frame.is_error_frame,
                )
                messages[key] = message
            message.add(source_row, frame)

            if observed_frames % _PROGRESS_STRIDE == 0 or observed_frames == expected_frames:
                context.progress.report(
                    observed_frames,
                    progress_total,
                    f"analysed {observed_frames} frames",
                )

        context.cancellation.raise_if_cancelled()
        timestamp_span_ns = (
            None
            if min_timestamp_ns is None or max_timestamp_ns is None
            else max_timestamp_ns - min_timestamp_ns
        )
        ordered_messages = [
            messages[key].to_payload()
            for key in sorted(messages, key=lambda item: (item[0], item[2], item[1], item[3], item[4]))
        ]
        payload = {
            "schema": "crt.session_statistics",
            "schema_version": SESSION_STATISTICS_ARTIFACT_SCHEMA_VERSION,
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
                "parameters": dict(analysis_input.parameters),
            },
            "session": {
                "id": source.id,
                "name": source.name,
                "source": source.source,
                "status": source.status,
                "declared_frame_count": source.frame_count,
                "reader_frame_count": expected_frames,
                "observed_frame_count": observed_frames,
                "marker_count": source.marker_count,
                "declared_duration_s": source.duration_s,
                "sha256": source.sha256,
            },
            "totals": {
                "frame_count": observed_frames,
                "payload_bytes": payload_bytes,
                "data_frame_count": data_frames,
                "remote_frame_count": remote_frames,
                "error_frame_count": error_frames,
                "standard_frame_count": standard_frames,
                "extended_frame_count": extended_frames,
                "unique_arbitration_id_count": len(arbitration_ids),
                "unique_message_key_count": len(messages),
                "first_sequence": first_sequence,
                "last_sequence": last_sequence,
                "first_timestamp_ns": first_timestamp_ns,
                "last_timestamp_ns": last_timestamp_ns,
                "min_timestamp_ns": min_timestamp_ns,
                "max_timestamp_ns": max_timestamp_ns,
                "timestamp_span_ns": timestamp_span_ns,
                "timestamp_span_s": (
                    None if timestamp_span_ns is None else _rounded(timestamp_span_ns / 1e9)
                ),
            },
            "capture_timing": capture_timing.to_payload(),
            "channels": _distribution(channel_counts, "channel"),
            "dlc_distribution": _distribution(dlc_counts, "dlc"),
            "messages": ordered_messages,
        }

        artifact = context.artifact_writer.write_json(
            filename="session-statistics.json",
            artifact_type="session_statistics",
            schema_version=SESSION_STATISTICS_ARTIFACT_SCHEMA_VERSION,
            sources=(
                ArtifactSource(
                    session_id=source.id,
                    source_kind="session",
                    source_reference={
                        "frame_count": observed_frames,
                        "sha256": source.sha256,
                    },
                ),
            ),
            payload=payload,
            metadata={
                "session_id": source.id,
                "frame_count": observed_frames,
                "message_key_count": len(messages),
            },
        )
        context.progress.report(progress_total, progress_total, "saved session statistics")
        return artifact


def _single_session_input(context: AnalysisContext):
    if len(context.inputs) != 1 or context.inputs[0].kind != "session":
        raise ValueError("session statistics requires exactly one session input")
    return context.inputs[0]


def _distribution(counts: dict[int, int], field_name: str) -> list[dict[str, int]]:
    return [{field_name: value, "frame_count": counts[value]} for value in sorted(counts)]


def _frame_kind(is_remote_frame: bool, is_error_frame: bool) -> str:
    if is_error_frame:
        return "error"
    if is_remote_frame:
        return "remote"
    return "data"


def _rounded(value: float) -> float:
    return round(float(value), 6)
