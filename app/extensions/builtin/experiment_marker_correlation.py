from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Mapping

from app.domain import Artifact, ArtifactSource
from app.models import CanFrame

from ..contracts import AnalysisContext, SessionSource
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType


EXPERIMENT_MARKER_CORRELATION_PROVIDER_ID = "crt.comparison.experiment_marker_correlation"
EXPERIMENT_MARKER_CORRELATION_PROVIDER_VERSION = "1.0.0"
EXPERIMENT_MARKER_CORRELATION_ALGORITHM_VERSION = "1"
EXPERIMENT_MARKER_CORRELATION_ARTIFACT_SCHEMA_VERSION = 1
_DEFAULT_PRE_WINDOW_MS = 250.0
_DEFAULT_POST_WINDOW_MS = 500.0
_DEFAULT_MAXIMUM_RANKED_CANDIDATES = 500
_DEFAULT_MAXIMUM_EVIDENCE_EVENTS = 32
_MAXIMUM_RANKED_CANDIDATES_LIMIT = 5000
_MAXIMUM_EVIDENCE_EVENTS_LIMIT = 256
_PROGRESS_STRIDE = 4096

MessageKey = tuple[int, int, bool, bool, bool]
CandidateKey = tuple[MessageKey, int, int]
ByteKey = tuple[MessageKey, int]


@dataclass(frozen=True, slots=True)
class _MarkerEvent:
    group: str
    session_id: str
    marker_id: str
    timestamp_ns: int
    preset_id: str
    name: str
    shortcut: str
    area: str
    source: str
    note: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "_MarkerEvent":
        group = str(payload.get("group", "")).strip().lower()
        if group not in {"target", "control"}:
            raise ValueError("marker event group must be target or control")
        session_id = str(payload.get("session_id", "")).strip()
        marker_id = str(payload.get("marker_id", "")).strip()
        if not session_id or not marker_id:
            raise ValueError("marker event requires session_id and marker_id")
        timestamp_ns = int(payload.get("timestamp_ns", -1))
        if timestamp_ns < 0:
            raise ValueError("marker timestamp cannot be negative")
        return cls(
            group=group,
            session_id=session_id,
            marker_id=marker_id,
            timestamp_ns=timestamp_ns,
            preset_id=str(payload.get("preset_id", "")),
            name=str(payload.get("name", "")),
            shortcut=str(payload.get("shortcut", "")),
            area=str(payload.get("area", "")),
            source=str(payload.get("source", "")),
            note=str(payload.get("note", "")),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "session_id": self.session_id,
            "marker_id": self.marker_id,
            "timestamp_ns": self.timestamp_ns,
            "preset_id": self.preset_id,
            "name": self.name,
            "shortcut": self.shortcut,
            "area": self.area,
            "source": self.source,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class _FrameEvidence:
    source_row: int
    sequence: int
    timestamp_ns: int
    dlc: int
    payload_hex: str

    @classmethod
    def from_frame(cls, source_row: int, frame: CanFrame) -> "_FrameEvidence":
        return cls(
            source_row=source_row,
            sequence=frame.sequence,
            timestamp_ns=frame.timestamp_ns,
            dlc=frame.dlc,
            payload_hex=frame.data_hex,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "source_row": self.source_row,
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "dlc": self.dlc,
            "payload_hex": self.payload_hex,
        }


@dataclass(slots=True)
class _EventWindow:
    marker: _MarkerEvent
    pre_start_ns: int
    post_end_ns: int
    pre_latest: dict[MessageKey, tuple[_FrameEvidence, bytes]] = field(default_factory=dict)
    post_last: dict[ByteKey, tuple[_FrameEvidence, int]] = field(default_factory=dict)
    first_change: dict[CandidateKey, tuple[_FrameEvidence, _FrameEvidence, int, int, int]] = field(default_factory=dict)

    def observe(self, source_row: int, frame: CanFrame) -> None:
        key = _message_key(frame)
        evidence = _FrameEvidence.from_frame(source_row, frame)
        if frame.timestamp_ns <= self.marker.timestamp_ns:
            self.pre_latest[key] = (evidence, frame.data)
            return
        baseline = self.pre_latest.get(key)
        if baseline is None:
            return
        before_evidence, before_data = baseline
        common = min(len(before_data), len(frame.data))
        for byte_index in range(common):
            before_byte = before_data[byte_index]
            after_byte = frame.data[byte_index]
            byte_key = (key, byte_index)
            self.post_last[byte_key] = (evidence, after_byte)
            changed = before_byte ^ after_byte
            if not changed:
                continue
            for bit_index in range(8):
                mask = 1 << bit_index
                if not changed & mask:
                    continue
                candidate = (key, byte_index, bit_index)
                if candidate in self.first_change:
                    continue
                self.first_change[candidate] = (
                    before_evidence,
                    evidence,
                    (before_byte >> bit_index) & 1,
                    (after_byte >> bit_index) & 1,
                    frame.timestamp_ns - self.marker.timestamp_ns,
                )

    def observations(self) -> dict[CandidateKey, dict[str, Any]]:
        result: dict[CandidateKey, dict[str, Any]] = {}
        for (message_key, byte_index), (last_evidence, last_byte) in self.post_last.items():
            baseline = self.pre_latest.get(message_key)
            if baseline is None:
                continue
            before_evidence, before_data = baseline
            if byte_index >= len(before_data):
                continue
            before_byte = before_data[byte_index]
            for bit_index in range(8):
                candidate = (message_key, byte_index, bit_index)
                changed = self.first_change.get(candidate)
                if changed is None:
                    result[candidate] = {
                        "changed": False,
                        "before_state": (before_byte >> bit_index) & 1,
                        "after_state": (last_byte >> bit_index) & 1,
                        "delay_ns": None,
                        "before": before_evidence,
                        "after": last_evidence,
                    }
                else:
                    before, after, before_state, after_state, delay_ns = changed
                    result[candidate] = {
                        "changed": True,
                        "before_state": before_state,
                        "after_state": after_state,
                        "delay_ns": delay_ns,
                        "before": before,
                        "after": after,
                    }
        return result


class ExperimentMarkerCorrelationProvider:
    """Deterministic passive marker-to-bit first-change correlation."""

    manifest = ExtensionManifest(
        id=EXPERIMENT_MARKER_CORRELATION_PROVIDER_ID,
        name="Experiment Diff / marker correlation",
        version=EXPERIMENT_MARKER_CORRELATION_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.COMPARISON,
        inputs=("comparison_set",),
        outputs=("experiment_marker_correlation",),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.SESSION_READ,
            ExtensionPermission.ARTIFACT_WRITE,
        ),
    )
    algorithm_version = EXPERIMENT_MARKER_CORRELATION_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input, comparison = _comparison_input(context)
        parameters = _parameters(analysis_input.parameters)
        events = tuple(_MarkerEvent.from_payload(item) for item in parameters["marker_events"])
        target_events = tuple(item for item in events if item.group == "target")
        control_events = tuple(item for item in events if item.group == "control")
        if not target_events:
            raise ValueError("experiment marker correlation requires at least one target marker event")

        allowed_sessions = set(comparison.session_ids)
        outside = sorted({event.session_id for event in events if event.session_id not in allowed_sessions})
        if outside:
            raise ValueError(f"marker events reference sessions outside comparison set: {outside}")

        sources = {session_id: context.project.session(session_id) for session_id in comparison.session_ids}
        events_by_session: dict[str, list[_MarkerEvent]] = defaultdict(list)
        for event in events:
            events_by_session[event.session_id].append(event)

        total_work = sum(source.frames.frame_count for source in sources.values()) + 1
        processed = 0
        context.progress.report(0, total_work, "correlating marker windows with immutable CAN frames")
        observations: dict[CandidateKey, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: {"target": [], "control": []}
        )
        event_summaries: list[dict[str, Any]] = []
        pre_ns = int(round(parameters["pre_window_ms"] * 1_000_000.0))
        post_ns = int(round(parameters["post_window_ms"] * 1_000_000.0))

        for session_id in comparison.session_ids:
            source = sources[session_id]
            session_events = sorted(events_by_session.get(session_id, ()), key=lambda item: (item.timestamp_ns, item.marker_id))
            windows = [
                _EventWindow(
                    marker=event,
                    pre_start_ns=max(0, event.timestamp_ns - pre_ns),
                    post_end_ns=event.timestamp_ns + post_ns,
                )
                for event in session_events
            ]
            active: list[_EventWindow] = []
            next_window = 0
            for source_row, frame in enumerate(source.frames.iter_frames()):
                context.cancellation.raise_if_cancelled()
                timestamp = frame.timestamp_ns
                while next_window < len(windows) and windows[next_window].pre_start_ns <= timestamp:
                    active.append(windows[next_window])
                    next_window += 1
                active = [window for window in active if timestamp <= window.post_end_ns]
                for window in active:
                    if window.pre_start_ns <= timestamp <= window.post_end_ns:
                        window.observe(source_row, frame)
                processed += 1
                if processed % _PROGRESS_STRIDE == 0:
                    context.progress.report(processed, total_work, f"analysed {processed} frames")

            for window in windows:
                event_observations = window.observations()
                changed_count = 0
                for candidate, observation in event_observations.items():
                    if observation["changed"]:
                        changed_count += 1
                    observations[candidate][window.marker.group].append(
                        {
                            **observation,
                            "marker": window.marker,
                            "session": source,
                        }
                    )
                event_summaries.append(
                    {
                        **window.marker.payload(),
                        "session_name": source.name,
                        "eligible_bit_candidate_count": len(event_observations),
                        "changed_bit_candidate_count": changed_count,
                    }
                )
            context.progress.report(processed, total_work, f"analysed markers in {source.name}")

        ranked = _rank_candidates(
            observations,
            target_event_count=len(target_events),
            control_event_count=len(control_events),
            maximum_evidence_events=parameters["maximum_evidence_events_per_candidate"],
        )
        all_count = len(ranked)
        ranked = ranked[: parameters["maximum_ranked_candidates"]]

        payload = {
            "schema": "crt.experiment_marker_correlation",
            "schema_version": EXPERIMENT_MARKER_CORRELATION_ARTIFACT_SCHEMA_VERSION,
            "generated_by": {
                "provider_id": self.manifest.id,
                "provider_version": self.manifest.version,
                "algorithm_version": self.algorithm_version,
                "crt_api": self.manifest.crt_api,
            },
            "project": {"id": context.project.project_id, "name": context.project.project_name},
            "input": {
                "kind": analysis_input.kind,
                "source_id": analysis_input.source_id,
                "parameters": {
                    key: value for key, value in parameters.items() if key != "marker_events"
                },
            },
            "comparison_set": {
                "id": comparison.id,
                "name": comparison.name,
                "session_ids": list(comparison.session_ids),
                "base_session_id": comparison.base_session_id,
                "synchronization_mode": comparison.synchronization_mode,
            },
            "marker_selection": {
                "target": parameters["target_marker"],
                "control": parameters["control_marker"],
                "target_event_count": len(target_events),
                "control_event_count": len(control_events),
                "pre_window_ms": parameters["pre_window_ms"],
                "post_window_ms": parameters["post_window_ms"],
            },
            "summary": {
                "session_count": len(comparison.session_ids),
                "target_event_count": len(target_events),
                "control_event_count": len(control_events),
                "candidate_count": all_count,
                "returned_candidate_count": len(ranked),
                "candidates_truncated": all_count > len(ranked),
            },
            "events": event_summaries,
            "ranked_candidates": ranked,
        }

        artifact_sources = tuple(
            ArtifactSource(
                session_id=source.id,
                source_kind="session",
                source_reference={
                    "comparison_set_id": comparison.id,
                    "frame_count": source.frames.frame_count,
                    "marker_event_count": len(events_by_session.get(source.id, ())),
                    "sha256": source.sha256,
                },
            )
            for source in sources.values()
        )
        artifact = context.artifact_writer.write_json(
            filename="experiment-marker-correlation.json",
            artifact_type="experiment_marker_correlation",
            schema_version=EXPERIMENT_MARKER_CORRELATION_ARTIFACT_SCHEMA_VERSION,
            sources=artifact_sources,
            payload=payload,
            metadata={
                "comparison_set_id": comparison.id,
                "target_event_count": len(target_events),
                "control_event_count": len(control_events),
                "candidate_count": all_count,
            },
        )
        context.progress.report(total_work, total_work, "saved experiment marker correlation")
        return artifact


def _rank_candidates(
    observations: Mapping[CandidateKey, Mapping[str, list[dict[str, Any]]]],
    *,
    target_event_count: int,
    control_event_count: int,
    maximum_evidence_events: int,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate, grouped in observations.items():
        target = grouped.get("target", [])
        control = grouped.get("control", [])
        target_changed = [item for item in target if item["changed"]]
        if not target_changed:
            continue
        control_changed = [item for item in control if item["changed"]]
        target_eligible = len(target)
        control_eligible = len(control)
        target_support = len(target_changed) / target_eligible if target_eligible else 0.0
        target_coverage = target_eligible / target_event_count if target_event_count else 0.0
        control_rate = len(control_changed) / control_eligible if control_eligible else 0.0
        specificity = 1.0 - control_rate if control_eligible else 1.0
        directions = Counter(
            f"{item['before_state']}->{item['after_state']}" for item in target_changed
        )
        dominant_direction, dominant_count = sorted(
            directions.items(), key=lambda item: (-item[1], item[0])
        )[0]
        direction_consistency = dominant_count / len(target_changed)
        score = target_support * target_coverage * specificity * direction_consistency
        delays = [int(item["delay_ns"]) for item in target_changed if item["delay_ns"] is not None]
        message_key, byte_index, bit_index = candidate
        evidence_rows = [
            _observation_payload(item) for item in (target_changed + control_changed)[:maximum_evidence_events]
        ]
        ranked.append(
            {
                **_message_key_payload(message_key),
                "byte_index": byte_index,
                "bit_index": bit_index,
                "candidate_key": f"{_message_key_payload(message_key)['message_key']}:B{byte_index}.{bit_index}",
                "score": _round(score),
                "target": {
                    "event_count": target_event_count,
                    "eligible_event_count": target_eligible,
                    "changed_event_count": len(target_changed),
                    "support_ratio": _round(target_support),
                    "coverage_ratio": _round(target_coverage),
                },
                "control": {
                    "event_count": control_event_count,
                    "eligible_event_count": control_eligible,
                    "changed_event_count": len(control_changed),
                    "change_ratio": _round(control_rate),
                    "specificity_ratio": _round(specificity),
                },
                "direction": {
                    "dominant": dominant_direction,
                    "consistency_ratio": _round(direction_consistency),
                    "counts": dict(sorted(directions.items())),
                },
                "timing": {
                    "sample_count": len(delays),
                    "min_delay_ns": min(delays) if delays else None,
                    "max_delay_ns": max(delays) if delays else None,
                    "mean_delay_ns": _round(sum(delays) / len(delays)) if delays else None,
                    "median_delay_ns": _round(float(median(delays))) if delays else None,
                },
                "evidence": evidence_rows,
                "evidence_event_count": len(target_changed) + len(control_changed),
                "evidence_truncated": len(target_changed) + len(control_changed) > len(evidence_rows),
            }
        )
    ranked.sort(
        key=lambda item: (
            -float(item["score"]),
            -int(item["target"]["changed_event_count"]),
            float(item["control"]["change_ratio"]),
            int(item["channel"]),
            bool(item["is_extended_id"]),
            int(item["arbitration_id"]),
            int(item["byte_index"]),
            int(item["bit_index"]),
        )
    )
    return ranked


def _observation_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    marker = item["marker"]
    source = item["session"]
    before = item["before"]
    after = item["after"]
    return {
        "group": marker.group,
        "session_id": source.id,
        "session_name": source.name,
        "marker": marker.payload(),
        "changed": bool(item["changed"]),
        "before_state": int(item["before_state"]),
        "after_state": int(item["after_state"]),
        "delay_ns": item["delay_ns"],
        "before": before.payload(),
        "after": after.payload(),
    }


def _comparison_input(context: AnalysisContext):
    if context.comparison is None:
        raise ValueError("experiment marker correlation requires comparison context")
    inputs = [item for item in context.inputs if item.kind == "comparison_set"]
    if len(inputs) != 1:
        raise ValueError("experiment marker correlation requires exactly one comparison_set input")
    if inputs[0].source_id != context.comparison.id:
        raise ValueError("comparison input does not match comparison context")
    return inputs[0], context.comparison


def _parameters(values: Mapping[str, Any]) -> dict[str, Any]:
    marker_events = values.get("marker_events")
    if not isinstance(marker_events, list):
        raise ValueError("marker_events must be a list")
    pre_window_ms = _bounded_float(values.get("pre_window_ms", _DEFAULT_PRE_WINDOW_MS), "pre_window_ms", 0.001, 60_000.0)
    post_window_ms = _bounded_float(values.get("post_window_ms", _DEFAULT_POST_WINDOW_MS), "post_window_ms", 0.001, 60_000.0)
    maximum_ranked_candidates = _bounded_int(
        values.get("maximum_ranked_candidates", _DEFAULT_MAXIMUM_RANKED_CANDIDATES),
        "maximum_ranked_candidates",
        1,
        _MAXIMUM_RANKED_CANDIDATES_LIMIT,
    )
    maximum_evidence_events = _bounded_int(
        values.get("maximum_evidence_events_per_candidate", _DEFAULT_MAXIMUM_EVIDENCE_EVENTS),
        "maximum_evidence_events_per_candidate",
        1,
        _MAXIMUM_EVIDENCE_EVENTS_LIMIT,
    )
    return {
        "target_marker": _selector_payload(values.get("target_marker")),
        "control_marker": _selector_payload(values.get("control_marker"), allow_empty=True),
        "pre_window_ms": pre_window_ms,
        "post_window_ms": post_window_ms,
        "maximum_ranked_candidates": maximum_ranked_candidates,
        "maximum_evidence_events_per_candidate": maximum_evidence_events,
        "marker_events": marker_events,
    }


def _selector_payload(value: object, *, allow_empty: bool = False) -> dict[str, Any] | None:
    if value is None and allow_empty:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("marker selector must be an object")
    selector = str(value.get("selector", "")).strip()
    if not selector:
        if allow_empty:
            return None
        raise ValueError("target marker selector cannot be empty")
    return {
        "selector": selector,
        "preset_id": str(value.get("preset_id", "")),
        "name": str(value.get("name", "")),
        "label": str(value.get("label", value.get("name", selector))),
    }


def _bounded_float(value: object, name: str, minimum: float, maximum: float) -> float:
    number = float(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def _bounded_int(value: object, name: str, minimum: int, maximum: int) -> int:
    number = int(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
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
        "message_key": f"{channel}:{'EXT' if extended else 'STD'}:{arbitration_id:0{width}X}:{kind}",
        "channel": channel,
        "arbitration_id": arbitration_id,
        "arbitration_id_hex": f"{arbitration_id:0{width}X}",
        "is_extended_id": extended,
        "frame_kind": kind,
        "is_remote_frame": remote,
        "is_error_frame": error,
    }


def _round(value: float) -> float:
    return round(float(value), 9)


__all__ = [
    "EXPERIMENT_MARKER_CORRELATION_ALGORITHM_VERSION",
    "EXPERIMENT_MARKER_CORRELATION_ARTIFACT_SCHEMA_VERSION",
    "EXPERIMENT_MARKER_CORRELATION_PROVIDER_ID",
    "EXPERIMENT_MARKER_CORRELATION_PROVIDER_VERSION",
    "ExperimentMarkerCorrelationProvider",
]
