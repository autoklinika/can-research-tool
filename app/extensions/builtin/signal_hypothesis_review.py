from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from app.domain import Artifact, ArtifactSource

from ..contracts import AnalysisContext, ArtifactSnapshot
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType


SIGNAL_HYPOTHESIS_REVIEW_PROVIDER_ID = "crt.comparison.signal_hypothesis_review"
SIGNAL_HYPOTHESIS_REVIEW_PROVIDER_VERSION = "1.0.0"
SIGNAL_HYPOTHESIS_REVIEW_ALGORITHM_VERSION = "1"
SIGNAL_HYPOTHESIS_REVIEW_ARTIFACT_SCHEMA_VERSION = 1

_ACTIONS = frozenset({"verify", "reject", "edit"})
_EDITABLE_FIELDS = (
    "name",
    "physical_meaning",
    "unit",
    "scale",
    "offset",
    "rationale",
)


class SignalHypothesisReviewProvider:
    """Persist an append-only operator decision for one Signal Hypothesis artifact."""

    manifest = ExtensionManifest(
        id=SIGNAL_HYPOTHESIS_REVIEW_PROVIDER_ID,
        name="Signal Hypothesis Operator Review",
        version=SIGNAL_HYPOTHESIS_REVIEW_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.COMPARISON,
        inputs=("comparison_set",),
        outputs=("signal_hypothesis_review",),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.ARTIFACT_READ,
            ExtensionPermission.ARTIFACT_WRITE,
        ),
    )
    algorithm_version = SIGNAL_HYPOTHESIS_REVIEW_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input, comparison = _comparison_input(context)
        parameters = _parameters(analysis_input.parameters)
        context.progress.report(0, 3, "reading Signal Hypothesis artifact")

        source = context.project.artifact(parameters["hypothesis_artifact_id"])
        _validate_hypothesis_artifact(source, comparison.id, comparison.session_ids)
        source_hypothesis = _mapping(source.payload.get("hypothesis"))
        source_candidate = _mapping(source.payload.get("source_candidate"))
        if not source_hypothesis:
            raise ValueError("Signal Hypothesis artifact has no hypothesis payload")

        action = parameters["action"]
        operator_note = parameters["operator_note"]
        if action == "reject" and not operator_note:
            raise ValueError("operator_note is required when rejecting a hypothesis")

        original_effective = _effective_from_source(source_hypothesis)
        if action == "reject":
            effective = dict(original_effective)
            edited_fields: list[str] = []
        else:
            effective = _effective_from_operator(
                parameters["operator_hypothesis"],
                source_hypothesis,
            )
            edited_fields = [
                key
                for key in _EDITABLE_FIELDS
                if effective.get(key) != original_effective.get(key)
            ]
            if action == "edit" and not edited_fields:
                raise ValueError("edit requires at least one changed hypothesis field")

        context.cancellation.raise_if_cancelled()
        context.progress.report(1, 3, "validated append-only operator decision")

        status = {
            "verify": "verified",
            "reject": "rejected",
            "edit": "edited",
        }[action]
        payload = {
            "schema": "crt.signal_hypothesis_review",
            "schema_version": SIGNAL_HYPOTHESIS_REVIEW_ARTIFACT_SCHEMA_VERSION,
            "generated_by": {
                "provider_id": self.manifest.id,
                "provider_version": self.manifest.version,
                "algorithm_version": self.algorithm_version,
                "crt_api": self.manifest.crt_api,
            },
            "comparison_set": {
                "id": comparison.id,
                "name": comparison.name,
                "session_ids": list(comparison.session_ids),
            },
            "source_hypothesis": {
                "artifact_id": source.id,
                "artifact_sha256": source.sha256,
                "schema_version": source.schema_version,
                "candidate_key": str(source_candidate.get("candidate_key", "")),
                "arbitration_id_hex": str(source_candidate.get("arbitration_id_hex", "")),
                "byte_index": _integer(source_candidate.get("byte_index"), default=-1),
                "bit_index": _integer(source_candidate.get("bit_index"), default=-1),
                "candidate_score": _number_or_none(source_candidate.get("candidate_score")),
                "strength": str(source_candidate.get("strength", "")),
                "ai_generated": bool(source_hypothesis.get("ai_generated", False)),
                "original_status": str(source_hypothesis.get("status", "suggested")),
                "original_verified": bool(source_hypothesis.get("verified", False)),
                "ai_confidence": _number_or_none(source_hypothesis.get("confidence")),
            },
            "review": {
                "action": action,
                "status": status,
                "verified": action == "verify",
                "rejected": action == "reject",
                "edited": bool(edited_fields),
                "operator_note": operator_note,
                "edited_fields": edited_fields,
            },
            "effective_hypothesis": effective,
            "guardrails": {
                "append_only": True,
                "source_hypothesis_modified": False,
                "source_of_truth_for_ai_evidence": "signal_hypothesis",
                "operator_decision_is_authoritative": True,
                "ai_used_for_review": False,
                "raw_session_access": False,
                "can_tx": False,
                "active_diagnostics": False,
            },
        }

        sources = tuple(
            ArtifactSource(
                session_id=session_id,
                source_kind="session",
                source_reference={
                    "comparison_set_id": comparison.id,
                    "hypothesis_artifact_id": source.id,
                    "hypothesis_artifact_sha256": source.sha256,
                    "review_action": action,
                },
            )
            for session_id in comparison.session_ids
        )
        artifact = context.artifact_writer.write_json(
            filename="signal-hypothesis-review.json",
            artifact_type="signal_hypothesis_review",
            schema_version=SIGNAL_HYPOTHESIS_REVIEW_ARTIFACT_SCHEMA_VERSION,
            sources=sources,
            payload=payload,
            metadata={
                "comparison_set_id": comparison.id,
                "hypothesis_artifact_id": source.id,
                "hypothesis_artifact_sha256": source.sha256,
                "candidate_key": str(source_candidate.get("candidate_key", "")),
                "review_action": action,
                "review_status": status,
                "verified": action == "verify",
                "rejected": action == "reject",
                "edited": bool(edited_fields),
            },
        )
        context.progress.report(3, 3, f"saved operator review: {status}")
        return artifact


def _effective_from_source(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": _required_text(source.get("name"), "name", 120),
        "physical_meaning": _required_text(
            source.get("physical_meaning"), "physical_meaning", 600
        ),
        "unit": _optional_text(source.get("unit"), 60),
        "scale": _finite_or_none(source.get("scale"), "scale"),
        "offset": _finite_or_none(source.get("offset"), "offset"),
        "rationale": _required_text(source.get("rationale"), "rationale", 1200),
        "next_experiments": _string_list(source.get("next_experiments"), maximum=5, limit=500),
        "warnings": _string_list(source.get("warnings"), maximum=5, limit=500),
    }


def _effective_from_operator(
    value: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    original = _effective_from_source(source)
    return {
        "name": _required_text(value.get("name"), "name", 120),
        "physical_meaning": _required_text(
            value.get("physical_meaning"), "physical_meaning", 600
        ),
        "unit": _optional_text(value.get("unit"), 60),
        "scale": _finite_or_none(value.get("scale"), "scale"),
        "offset": _finite_or_none(value.get("offset"), "offset"),
        "rationale": _required_text(value.get("rationale"), "rationale", 1200),
        "next_experiments": original["next_experiments"],
        "warnings": original["warnings"],
    }


def _validate_hypothesis_artifact(
    artifact: ArtifactSnapshot,
    comparison_set_id: str,
    comparison_session_ids: Sequence[str],
) -> None:
    if artifact.artifact_type != "signal_hypothesis":
        raise ValueError(f"artifact {artifact.id} is not signal_hypothesis")
    if artifact.schema_version != 2:
        raise ValueError(f"unsupported Signal Hypothesis schema {artifact.schema_version}")
    payload = artifact.payload
    if payload.get("schema") != "crt.signal_hypothesis":
        raise ValueError("unexpected Signal Hypothesis payload schema")
    comparison = _mapping(payload.get("comparison_set"))
    if str(comparison.get("id", "")) != comparison_set_id:
        raise ValueError("Signal Hypothesis artifact belongs to another comparison set")
    sessions = tuple(str(item) for item in comparison.get("session_ids", ()))
    if sessions and set(sessions) != set(comparison_session_ids):
        raise ValueError("Signal Hypothesis artifact has incompatible session set")


def _parameters(values: Mapping[str, Any]) -> dict[str, Any]:
    hypothesis_artifact_id = str(values.get("hypothesis_artifact_id", "")).strip()
    action = str(values.get("action", "")).strip().lower()
    if not hypothesis_artifact_id:
        raise ValueError("hypothesis_artifact_id is required")
    if action not in _ACTIONS:
        raise ValueError("action must be verify, reject or edit")
    operator_hypothesis = values.get("operator_hypothesis")
    if action != "reject" and not isinstance(operator_hypothesis, Mapping):
        raise ValueError("operator_hypothesis is required for verify/edit")
    return {
        "hypothesis_artifact_id": hypothesis_artifact_id,
        "action": action,
        "operator_note": str(values.get("operator_note", "") or "").strip()[:1000],
        "operator_hypothesis": dict(operator_hypothesis) if isinstance(operator_hypothesis, Mapping) else {},
    }


def _comparison_input(context: AnalysisContext):
    if context.comparison is None:
        raise ValueError("Signal Hypothesis Review requires comparison context")
    inputs = [item for item in context.inputs if item.kind == "comparison_set"]
    if len(inputs) != 1 or inputs[0].source_id != context.comparison.id:
        raise ValueError(
            "Signal Hypothesis Review requires exactly one matching comparison_set input"
        )
    return inputs[0], context.comparison


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _required_text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    text = value.strip()[:limit]
    if not text:
        raise ValueError(f"{field} cannot be empty")
    return text


def _optional_text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()[:limit]
    return text or None


def _finite_or_none(value: object, field: str) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number or empty")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number or empty") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number or empty")
    return number


def _string_list(value: object, *, maximum: int, limit: int) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip()[:limit])
        if len(result) >= maximum:
            break
    return result


def _integer(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number_or_none(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


__all__ = [
    "SIGNAL_HYPOTHESIS_REVIEW_ALGORITHM_VERSION",
    "SIGNAL_HYPOTHESIS_REVIEW_ARTIFACT_SCHEMA_VERSION",
    "SIGNAL_HYPOTHESIS_REVIEW_PROVIDER_ID",
    "SIGNAL_HYPOTHESIS_REVIEW_PROVIDER_VERSION",
    "SignalHypothesisReviewProvider",
]
