from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from app.domain import Artifact, ArtifactSource

from ..contracts import AnalysisContext, ArtifactSnapshot
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType


SIGNAL_CANDIDATE_ENGINE_PROVIDER_ID = "crt.comparison.signal_candidate_engine"
SIGNAL_CANDIDATE_ENGINE_PROVIDER_VERSION = "1.0.0"
SIGNAL_CANDIDATE_ENGINE_ALGORITHM_VERSION = "1"
SIGNAL_CANDIDATE_ENGINE_ARTIFACT_SCHEMA_VERSION = 1

_DEFAULT_MAXIMUM_CANDIDATES = 500
_DEFAULT_MAXIMUM_EVIDENCE_EVENTS = 64
_MAXIMUM_CANDIDATES_LIMIT = 5000
_MAXIMUM_EVIDENCE_EVENTS_LIMIT = 512


class SignalCandidateEngineProvider:
    """Consolidate deterministic Experiment Diff evidence into signal candidates."""

    manifest = ExtensionManifest(
        id=SIGNAL_CANDIDATE_ENGINE_PROVIDER_ID,
        name="Signal Candidate Engine",
        version=SIGNAL_CANDIDATE_ENGINE_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.COMPARISON,
        inputs=("comparison_set",),
        outputs=("signal_candidates",),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.ARTIFACT_READ,
            ExtensionPermission.ARTIFACT_WRITE,
        ),
    )
    algorithm_version = SIGNAL_CANDIDATE_ENGINE_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input, comparison = _comparison_input(context)
        parameters = _parameters(analysis_input.parameters)
        experiment_ids = parameters["experiment_artifact_ids"]
        discovery_ids = parameters["signal_discovery_artifact_ids"]
        total = len(experiment_ids) + len(discovery_ids) + 2
        current = 0
        context.progress.report(current, total, "reading deterministic source artifacts")

        experiment_artifacts: list[ArtifactSnapshot] = []
        for artifact_id in experiment_ids:
            context.cancellation.raise_if_cancelled()
            snapshot = context.project.artifact(artifact_id)
            _validate_experiment_artifact(snapshot, comparison.id, comparison.session_ids)
            experiment_artifacts.append(snapshot)
            current += 1
            context.progress.report(
                current,
                total,
                f"loaded Experiment Diff artifact {current}/{len(experiment_ids)}",
            )

        discovery_artifacts: list[ArtifactSnapshot] = []
        for index, artifact_id in enumerate(discovery_ids, start=1):
            context.cancellation.raise_if_cancelled()
            snapshot = context.project.artifact(artifact_id)
            _validate_signal_discovery_artifact(snapshot, comparison.session_ids)
            discovery_artifacts.append(snapshot)
            current += 1
            context.progress.report(
                current,
                total,
                f"loaded Signal Discovery artifact {index}/{len(discovery_ids)}",
            )

        activity_index = _build_activity_index(discovery_artifacts)
        candidates = _consolidate_candidates(
            experiment_artifacts,
            activity_index=activity_index,
            comparison_session_ids=comparison.session_ids,
            maximum_evidence_events=parameters["maximum_evidence_events_per_candidate"],
        )
        all_candidate_count = len(candidates)
        candidates = candidates[: parameters["maximum_candidates"]]
        current += 1
        context.progress.report(current, total, "ranked deterministic signal candidates")

        payload = {
            "schema": "crt.signal_candidates",
            "schema_version": SIGNAL_CANDIDATE_ENGINE_ARTIFACT_SCHEMA_VERSION,
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
            "comparison_set": {
                "id": comparison.id,
                "name": comparison.name,
                "session_ids": list(comparison.session_ids),
                "base_session_id": comparison.base_session_id,
                "synchronization_mode": comparison.synchronization_mode,
            },
            "inputs": {
                "experiment_artifacts": [
                    _artifact_reference(item) for item in experiment_artifacts
                ],
                "signal_discovery_artifacts": [
                    _artifact_reference(item) for item in discovery_artifacts
                ],
            },
            "ranking_contract": {
                "candidate_score": "best Experiment Diff deterministic score",
                "signal_discovery_role": (
                    "validation/enrichment only; missing activity artifacts do not reduce score"
                ),
                "strength": {
                    "strong": (
                        "score>=0.75, target changes>=3, direction consistency>=0.80, "
                        "control change ratio<=0.25, no inconsistent activity evidence"
                    ),
                    "medium": "score>=0.40 and target changes>=2",
                    "weak": "all remaining candidates",
                },
                "ai_used": False,
            },
            "summary": {
                "experiment_artifact_count": len(experiment_artifacts),
                "signal_discovery_artifact_count": len(discovery_artifacts),
                "candidate_count": all_candidate_count,
                "returned_candidate_count": len(candidates),
                "candidates_truncated": all_candidate_count > len(candidates),
                "strong_count": sum(1 for item in candidates if item["strength"] == "strong"),
                "medium_count": sum(1 for item in candidates if item["strength"] == "medium"),
                "weak_count": sum(1 for item in candidates if item["strength"] == "weak"),
            },
            "candidates": candidates,
        }

        artifact_sources = tuple(
            ArtifactSource(
                session_id=session_id,
                source_kind="session",
                source_reference={
                    "comparison_set_id": comparison.id,
                    "experiment_artifact_ids": list(experiment_ids),
                    "signal_discovery_artifact_ids": list(discovery_ids),
                },
            )
            for session_id in comparison.session_ids
        )
        artifact = context.artifact_writer.write_json(
            filename="signal-candidates.json",
            artifact_type="signal_candidates",
            schema_version=SIGNAL_CANDIDATE_ENGINE_ARTIFACT_SCHEMA_VERSION,
            sources=artifact_sources,
            payload=payload,
            metadata={
                "comparison_set_id": comparison.id,
                "experiment_artifact_count": len(experiment_artifacts),
                "signal_discovery_artifact_count": len(discovery_artifacts),
                "candidate_count": all_candidate_count,
                "strong_count": payload["summary"]["strong_count"],
            },
        )
        context.progress.report(total, total, "saved Signal Candidate Engine artifact")
        return artifact


def _consolidate_candidates(
    experiment_artifacts: Sequence[ArtifactSnapshot],
    *,
    activity_index: Mapping[tuple[str, int, int], tuple[dict[str, Any], ...]],
    comparison_session_ids: Sequence[str],
    maximum_evidence_events: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identities: dict[str, dict[str, Any]] = {}

    for artifact in experiment_artifacts:
        payload = artifact.payload
        selection = _mapping(payload.get("marker_selection"))
        target_selection = _mapping(selection.get("target"))
        control_selection = _mapping(selection.get("control"))
        experiment = {
            "artifact_id": artifact.id,
            "artifact_sha256": artifact.sha256,
            "created_at_utc": artifact.created_at_utc,
            "target": {
                "selector": target_selection.get("selector", ""),
                "name": target_selection.get("name", ""),
                "label": target_selection.get("label", target_selection.get("name", "")),
                "event_count": _integer(selection.get("target_event_count")),
            },
            "control": {
                "selector": control_selection.get("selector", ""),
                "name": control_selection.get("name", ""),
                "label": control_selection.get("label", control_selection.get("name", "")),
                "event_count": _integer(selection.get("control_event_count")),
            }
            if control_selection
            else None,
            "pre_window_ms": _number_or_none(selection.get("pre_window_ms")),
            "post_window_ms": _number_or_none(selection.get("post_window_ms")),
        }
        rows = payload.get("ranked_candidates")
        if not isinstance(rows, (list, tuple)):
            raise ValueError(f"Experiment Diff artifact {artifact.id} has no ranked_candidates")
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            identity = _candidate_identity(row)
            candidate_key = identity["candidate_key"]
            identities.setdefault(candidate_key, identity)
            target = _mapping(row.get("target"))
            control = _mapping(row.get("control"))
            direction = _mapping(row.get("direction"))
            timing = _mapping(row.get("timing"))
            evidence = row.get("evidence")
            evidence_rows = [
                dict(item)
                for item in evidence
                if isinstance(item, Mapping)
            ] if isinstance(evidence, (list, tuple)) else []
            grouped[candidate_key].append(
                {
                    "experiment": experiment,
                    "score": _bounded_ratio(row.get("score")),
                    "target": dict(target),
                    "control": dict(control),
                    "direction": dict(direction),
                    "timing": dict(timing),
                    "evidence": evidence_rows,
                    "evidence_event_count": _integer(row.get("evidence_event_count")),
                    "evidence_truncated": bool(row.get("evidence_truncated", False)),
                }
            )

    ranked: list[dict[str, Any]] = []
    for candidate_key, supports in grouped.items():
        supports.sort(key=_support_sort_key)
        best = supports[0]
        activity = _activity_summary(
            candidate_key,
            activity_index,
            comparison_session_ids=comparison_session_ids,
        )
        strength = _strength(best, activity)
        evidence: list[dict[str, Any]] = []
        total_evidence_count = 0
        for support in supports:
            experiment = support["experiment"]
            rows = support["evidence"]
            total_evidence_count += max(len(rows), support["evidence_event_count"])
            for row in rows:
                if len(evidence) >= maximum_evidence_events:
                    break
                evidence.append(
                    {
                        **row,
                        "experiment_artifact_id": experiment["artifact_id"],
                        "experiment_target": experiment["target"],
                        "experiment_control": experiment["control"],
                    }
                )
            if len(evidence) >= maximum_evidence_events:
                break

        identity = identities[candidate_key]
        ranked.append(
            {
                **identity,
                "candidate_score": best["score"],
                "strength": strength,
                "support_count": len(supports),
                "strong_support_count": sum(
                    1 for support in supports if _support_is_strong(support)
                ),
                "best_support": _public_support(best),
                "supports": [_public_support(item) for item in supports],
                "activity_validation": activity,
                "evidence": evidence,
                "evidence_event_count": total_evidence_count,
                "evidence_truncated": total_evidence_count > len(evidence),
            }
        )

    strength_rank = {"strong": 0, "medium": 1, "weak": 2}
    ranked.sort(
        key=lambda item: (
            -float(item["candidate_score"]),
            strength_rank[item["strength"]],
            -int(item["best_support"]["target"].get("changed_event_count", 0)),
            -float(item["activity_validation"].get("coverage_ratio", 0.0)),
            int(item["channel"]),
            bool(item["is_extended_id"]),
            int(item["arbitration_id"]),
            int(item["byte_index"]),
            int(item["bit_index"]),
        )
    )
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank"] = index
    return ranked


def _build_activity_index(
    artifacts: Sequence[ArtifactSnapshot],
) -> dict[tuple[str, int, int], tuple[dict[str, Any], ...]]:
    grouped: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for artifact in artifacts:
        payload = artifact.payload
        session = _mapping(payload.get("session"))
        message_key_payload = _mapping(payload.get("message_key"))
        message_key = _message_key_from_discovery(message_key_payload)
        bytes_payload = payload.get("bytes")
        if not isinstance(bytes_payload, (list, tuple)):
            continue
        for byte_row in bytes_payload:
            if not isinstance(byte_row, Mapping):
                continue
            byte_index = _integer(byte_row.get("byte"), default=-1)
            if byte_index < 0:
                continue
            present_count = _integer(byte_row.get("present_count"))
            bits = byte_row.get("bits")
            if not isinstance(bits, (list, tuple)):
                continue
            for bit_row in bits:
                if not isinstance(bit_row, Mapping):
                    continue
                bit_index = _integer(bit_row.get("bit"), default=-1)
                if not 0 <= bit_index <= 7:
                    continue
                grouped[(message_key, byte_index, bit_index)].append(
                    {
                        "artifact_id": artifact.id,
                        "artifact_sha256": artifact.sha256,
                        "session_id": str(session.get("id", "")),
                        "session_name": str(session.get("name", "")),
                        "present_count": present_count,
                        "constant": bool(bit_row.get("constant", False)),
                        "set_count": _integer(bit_row.get("set_count")),
                        "clear_count": _integer(bit_row.get("clear_count")),
                        "transition_count": _integer(bit_row.get("transition_count")),
                        "transition_opportunity_count": _integer(
                            bit_row.get("transition_opportunity_count")
                        ),
                        "transition_rate": _bounded_ratio(bit_row.get("transition_rate")),
                        "set_ratio": _bounded_ratio(bit_row.get("set_ratio")),
                    }
                )
    return {key: tuple(value) for key, value in grouped.items()}


def _activity_summary(
    candidate_key: str,
    activity_index: Mapping[tuple[str, int, int], tuple[dict[str, Any], ...]],
    *,
    comparison_session_ids: Sequence[str],
) -> dict[str, Any]:
    message_key, byte_index, bit_index = _split_candidate_key(candidate_key)
    observations = list(activity_index.get((message_key, byte_index, bit_index), ()))
    if not observations:
        return {
            "status": "unavailable",
            "artifact_count": 0,
            "session_count": 0,
            "comparison_session_count": len(comparison_session_ids),
            "coverage_ratio": 0.0,
            "variable_observation_count": 0,
            "constant_observation_count": 0,
            "variable_ratio": None,
            "transition_count": 0,
            "transition_opportunity_count": 0,
            "transition_rate": None,
            "set_ratio": None,
            "artifacts": [],
        }
    sessions = {item["session_id"] for item in observations if item["session_id"]}
    variable = [item for item in observations if not item["constant"]]
    transition_count = sum(item["transition_count"] for item in observations)
    opportunities = sum(item["transition_opportunity_count"] for item in observations)
    set_count = sum(item["set_count"] for item in observations)
    present_count = sum(item["present_count"] for item in observations)
    status = "consistent" if variable else "inconsistent"
    return {
        "status": status,
        "artifact_count": len(observations),
        "session_count": len(sessions),
        "comparison_session_count": len(comparison_session_ids),
        "coverage_ratio": _round(len(sessions) / len(comparison_session_ids))
        if comparison_session_ids
        else 0.0,
        "variable_observation_count": len(variable),
        "constant_observation_count": len(observations) - len(variable),
        "variable_ratio": _round(len(variable) / len(observations)),
        "transition_count": transition_count,
        "transition_opportunity_count": opportunities,
        "transition_rate": _round(transition_count / opportunities)
        if opportunities
        else 0.0,
        "set_ratio": _round(set_count / present_count) if present_count else None,
        "artifacts": observations,
    }


def _strength(best: Mapping[str, Any], activity: Mapping[str, Any]) -> str:
    score = float(best.get("score", 0.0))
    target = _mapping(best.get("target"))
    control = _mapping(best.get("control"))
    direction = _mapping(best.get("direction"))
    target_changes = _integer(target.get("changed_event_count"))
    control_change_ratio = _bounded_ratio(control.get("change_ratio"))
    direction_consistency = _bounded_ratio(direction.get("consistency_ratio"))
    if (
        score >= 0.75
        and target_changes >= 3
        and direction_consistency >= 0.80
        and control_change_ratio <= 0.25
        and activity.get("status") != "inconsistent"
    ):
        return "strong"
    if score >= 0.40 and target_changes >= 2:
        return "medium"
    return "weak"


def _support_is_strong(support: Mapping[str, Any]) -> bool:
    target = _mapping(support.get("target"))
    control = _mapping(support.get("control"))
    direction = _mapping(support.get("direction"))
    return (
        float(support.get("score", 0.0)) >= 0.75
        and _integer(target.get("changed_event_count")) >= 3
        and _bounded_ratio(direction.get("consistency_ratio")) >= 0.80
        and _bounded_ratio(control.get("change_ratio")) <= 0.25
    )


def _public_support(support: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "experiment": support["experiment"],
        "score": support["score"],
        "target": support["target"],
        "control": support["control"],
        "direction": support["direction"],
        "timing": support["timing"],
        "evidence_event_count": support["evidence_event_count"],
        "evidence_truncated": support["evidence_truncated"],
    }


def _support_sort_key(support: Mapping[str, Any]) -> tuple[Any, ...]:
    target = _mapping(support.get("target"))
    control = _mapping(support.get("control"))
    experiment = _mapping(support.get("experiment"))
    return (
        -float(support.get("score", 0.0)),
        -_integer(target.get("changed_event_count")),
        _bounded_ratio(control.get("change_ratio")),
        str(experiment.get("artifact_id", "")),
    )


def _candidate_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    message_key = str(row.get("message_key", "")).strip()
    byte_index = _integer(row.get("byte_index"), default=-1)
    bit_index = _integer(row.get("bit_index"), default=-1)
    if not message_key or byte_index < 0 or not 0 <= bit_index <= 7:
        raise ValueError("Experiment Diff candidate has invalid identity")
    expected = f"{message_key}:B{byte_index}.{bit_index}"
    candidate_key = str(row.get("candidate_key", expected)).strip()
    if candidate_key != expected:
        raise ValueError(
            f"Experiment Diff candidate_key mismatch: expected {expected}, got {candidate_key}"
        )
    return {
        "candidate_key": candidate_key,
        "message_key": message_key,
        "channel": _integer(row.get("channel")),
        "arbitration_id": _integer(row.get("arbitration_id")),
        "arbitration_id_hex": str(row.get("arbitration_id_hex", "")),
        "is_extended_id": bool(row.get("is_extended_id", False)),
        "frame_kind": str(row.get("frame_kind", "data")),
        "byte_index": byte_index,
        "bit_index": bit_index,
    }


def _message_key_from_discovery(payload: Mapping[str, Any]) -> str:
    channel = _integer(payload.get("channel"))
    arbitration_id = _integer(payload.get("arbitration_id"))
    extended = bool(payload.get("is_extended_id", False))
    frame_kind = str(payload.get("frame_kind", "data")).strip().lower()
    width = 8 if extended else 3
    return f"{channel}:{'EXT' if extended else 'STD'}:{arbitration_id:0{width}X}:{frame_kind}"


def _split_candidate_key(candidate_key: str) -> tuple[str, int, int]:
    try:
        message_key, bitfield = candidate_key.rsplit(":B", 1)
        byte_text, bit_text = bitfield.split(".", 1)
        return message_key, int(byte_text), int(bit_text)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid candidate_key: {candidate_key}") from exc


def _validate_experiment_artifact(
    artifact: ArtifactSnapshot,
    comparison_set_id: str,
    comparison_session_ids: Sequence[str],
) -> None:
    if artifact.artifact_type != "experiment_marker_correlation":
        raise ValueError(
            f"artifact {artifact.id} is not experiment_marker_correlation"
        )
    if artifact.schema_version != 1:
        raise ValueError(
            f"unsupported Experiment Diff schema {artifact.schema_version}: {artifact.id}"
        )
    payload = artifact.payload
    if payload.get("schema") != "crt.experiment_marker_correlation":
        raise ValueError(f"artifact {artifact.id} has unexpected Experiment Diff schema")
    comparison = _mapping(payload.get("comparison_set"))
    if comparison.get("id") != comparison_set_id:
        raise ValueError(
            f"Experiment Diff artifact {artifact.id} belongs to another comparison set"
        )
    sessions = tuple(str(item) for item in comparison.get("session_ids", ()))
    if sessions and set(sessions) != set(comparison_session_ids):
        raise ValueError(
            f"Experiment Diff artifact {artifact.id} has incompatible session set"
        )


def _validate_signal_discovery_artifact(
    artifact: ArtifactSnapshot,
    comparison_session_ids: Sequence[str],
) -> None:
    if artifact.artifact_type != "signal_discovery_activity":
        raise ValueError(f"artifact {artifact.id} is not signal_discovery_activity")
    if artifact.schema_version != 1:
        raise ValueError(
            f"unsupported Signal Discovery schema {artifact.schema_version}: {artifact.id}"
        )
    payload = artifact.payload
    if payload.get("schema") != "crt.signal_discovery_activity":
        raise ValueError(f"artifact {artifact.id} has unexpected Signal Discovery schema")
    session = _mapping(payload.get("session"))
    if str(session.get("id", "")) not in comparison_session_ids:
        raise ValueError(
            f"Signal Discovery artifact {artifact.id} references a session outside comparison set"
        )


def _artifact_reference(artifact: ArtifactSnapshot) -> dict[str, Any]:
    return {
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "schema_version": artifact.schema_version,
        "provider_id": artifact.provider_id,
        "provider_version": artifact.provider_version,
        "algorithm_version": artifact.algorithm_version,
        "sha256": artifact.sha256,
        "created_at_utc": artifact.created_at_utc,
    }


def _comparison_input(context: AnalysisContext):
    if context.comparison is None:
        raise ValueError("Signal Candidate Engine requires comparison context")
    inputs = [item for item in context.inputs if item.kind == "comparison_set"]
    if len(inputs) != 1:
        raise ValueError(
            "Signal Candidate Engine requires exactly one comparison_set input"
        )
    if inputs[0].source_id != context.comparison.id:
        raise ValueError("comparison input does not match comparison context")
    return inputs[0], context.comparison


def _parameters(values: Mapping[str, Any]) -> dict[str, Any]:
    experiment_ids = _artifact_ids(values.get("experiment_artifact_ids"), required=True)
    discovery_ids = _artifact_ids(
        values.get("signal_discovery_artifact_ids", ()), required=False
    )
    overlap = sorted(set(experiment_ids) & set(discovery_ids))
    if overlap:
        raise ValueError(f"artifact cannot be both Experiment Diff and Signal Discovery: {overlap}")
    return {
        "experiment_artifact_ids": experiment_ids,
        "signal_discovery_artifact_ids": discovery_ids,
        "maximum_candidates": _bounded_int(
            values.get("maximum_candidates", _DEFAULT_MAXIMUM_CANDIDATES),
            "maximum_candidates",
            1,
            _MAXIMUM_CANDIDATES_LIMIT,
        ),
        "maximum_evidence_events_per_candidate": _bounded_int(
            values.get(
                "maximum_evidence_events_per_candidate",
                _DEFAULT_MAXIMUM_EVIDENCE_EVENTS,
            ),
            "maximum_evidence_events_per_candidate",
            1,
            _MAXIMUM_EVIDENCE_EVENTS_LIMIT,
        ),
    }


def _artifact_ids(value: object, *, required: bool) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("artifact id collection must be a list")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if required and not result:
        raise ValueError("Signal Candidate Engine requires Experiment Diff artifacts")
    if len(result) != len(set(result)):
        raise ValueError("artifact ids must be unique")
    return result


def _bounded_int(value: object, name: str, minimum: int, maximum: int) -> int:
    number = int(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _integer(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number_or_none(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _bounded_ratio(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return _round(max(0.0, min(1.0, number)))


def _round(value: float) -> float:
    return round(float(value), 9)


__all__ = [
    "SIGNAL_CANDIDATE_ENGINE_ALGORITHM_VERSION",
    "SIGNAL_CANDIDATE_ENGINE_ARTIFACT_SCHEMA_VERSION",
    "SIGNAL_CANDIDATE_ENGINE_PROVIDER_ID",
    "SIGNAL_CANDIDATE_ENGINE_PROVIDER_VERSION",
    "SignalCandidateEngineProvider",
]
