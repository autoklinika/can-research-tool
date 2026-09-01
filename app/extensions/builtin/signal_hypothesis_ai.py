from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from app.domain import Artifact, ArtifactSource
from app.local_ai import LocalAIError, extract_json_object

from ..contracts import AnalysisContext, ArtifactSnapshot
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType


SIGNAL_HYPOTHESIS_PROVIDER_ID = "crt.comparison.signal_hypothesis_ai"
SIGNAL_HYPOTHESIS_PROVIDER_VERSION = "1.0.2"
SIGNAL_HYPOTHESIS_ALGORITHM_VERSION = "3"
SIGNAL_HYPOTHESIS_ARTIFACT_SCHEMA_VERSION = 2

_DEFAULT_MAXIMUM_EVIDENCE_EVENTS = 8
_MAXIMUM_EVIDENCE_EVENTS_LIMIT = 32
_REQUIRED_HYPOTHESIS_KEYS = frozenset(
    {
        "name",
        "physical_meaning",
        "unit",
        "scale",
        "offset",
        "confidence",
        "rationale",
        "next_experiments",
        "warnings",
    }
)

_SYSTEM_PROMPT = """You are the optional local AI interpretation layer in CRT, a CAN reverse-engineering workstation.
The deterministic signal_candidates artifact is the source of truth. You must never change its score, class, counts, direction or evidence and you must never describe a hypothesis as confirmed.
Infer only a cautious, testable signal hypothesis from the supplied structured candidate data. Marker/experiment names are operator labels and may be suggestive, but are not proof of physical meaning.
Return exactly one JSON object. Do not include markdown, prose outside JSON, hidden chain-of-thought, or an empty object. Always return every required key:
{
  "name": string,
  "physical_meaning": string,
  "unit": string or null,
  "scale": number or null,
  "offset": number or null,
  "confidence": number from 0 to 1,
  "rationale": string,
  "next_experiments": array of strings,
  "warnings": array of strings
}
Never use an empty string for name, physical_meaning or rationale. next_experiments and warnings must each contain at least one concrete item.
If unit, scale or offset cannot be justified, return null for that field.
If the physical meaning cannot be identified from the evidence, do not refuse and do not return {}. Use a neutral name such as "unknown_bit_state_candidate", explicitly state in physical_meaning that the bit is only correlated with the observed experiment and its physical meaning is unknown, use low confidence, explain the uncertainty in rationale, propose at least one discriminating verification experiment, and warn that marker labels are not proof.
A strong deterministic candidate score means strong correlation in the supplied experiment; it does not by itself prove semantic meaning.
"""


class SignalHypothesisAIProvider:
    """Generate a non-authoritative hypothesis from one deterministic signal candidate."""

    manifest = ExtensionManifest(
        id=SIGNAL_HYPOTHESIS_PROVIDER_ID,
        name="Signal Hypothesis AI",
        version=SIGNAL_HYPOTHESIS_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.COMPARISON,
        inputs=("comparison_set",),
        outputs=("signal_hypothesis",),
        requires_ai=True,
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.ARTIFACT_READ,
            ExtensionPermission.ARTIFACT_WRITE,
            ExtensionPermission.AI_USE,
        ),
    )
    algorithm_version = SIGNAL_HYPOTHESIS_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input, comparison = _comparison_input(context)
        parameters = _parameters(analysis_input.parameters)
        if context.ai_client is None:
            raise ValueError("Signal Hypothesis requires a configured local AI client")

        context.progress.report(0, 4, "reading deterministic Signal Candidates artifact")
        source = context.project.artifact(parameters["candidate_artifact_id"])
        _validate_candidate_artifact(source, comparison.id, comparison.session_ids)
        candidate = _find_candidate(source.payload, parameters["candidate_key"])
        context.cancellation.raise_if_cancelled()

        ai_context = _ai_context(
            source,
            candidate,
            maximum_evidence_events=parameters["maximum_evidence_events"],
            user_context=parameters["user_context"],
        )
        context.progress.report(1, 4, "prepared bounded candidate context for local AI")
        completion = context.ai_client.complete(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=json.dumps(ai_context, ensure_ascii=False, sort_keys=True, indent=2),
            cancellation=context.cancellation,
        )
        context.progress.report(2, 4, "local AI response received; validating hypothesis")
        try:
            response = extract_json_object(completion.content)
            hypothesis = _normalize_hypothesis(response)
        except LocalAIError as exc:
            raise LocalAIError(
                f"AI response rejected (model={completion.model}): {exc}; "
                f"response_excerpt={_response_excerpt(completion.content)}"
            ) from exc
        context.cancellation.raise_if_cancelled()

        candidate_identity = _candidate_identity(candidate)
        response_sha256 = hashlib.sha256(completion.content.encode("utf-8")).hexdigest()
        payload = {
            "schema": "crt.signal_hypothesis",
            "schema_version": SIGNAL_HYPOTHESIS_ARTIFACT_SCHEMA_VERSION,
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
            "source_candidate": {
                "artifact_id": source.id,
                "artifact_sha256": source.sha256,
                **candidate_identity,
                "rank": _integer(candidate.get("rank")),
                "strength": str(candidate.get("strength", "")),
                "candidate_score": _ratio(candidate.get("candidate_score")),
                "best_support": _json_value(candidate.get("best_support")),
                "activity_validation": _json_value(candidate.get("activity_validation")),
            },
            "hypothesis": {
                "status": "suggested",
                "verified": False,
                "ai_generated": True,
                **hypothesis,
            },
            "ai": {
                "provider": completion.provider,
                "model": completion.model,
                "endpoint": completion.endpoint,
                "latency_ms": completion.latency_ms,
                "usage": dict(completion.usage),
                "response_format": "json_object",
                "response_contract_version": 2,
                "response_sha256": response_sha256,
            },
            "guardrails": {
                "source_of_truth": "signal_candidates",
                "candidate_score_modified": False,
                "raw_session_access": False,
                "can_tx": False,
                "active_diagnostics": False,
                "automatic_confirmation": False,
                "ai_failure_blocks_crt": False,
                "semantic_response_validation": True,
            },
            "context_sent_to_ai": {
                "raw_session_included": False,
                "candidate_artifact_id": source.id,
                "candidate_key": candidate_identity["candidate_key"],
                "evidence_events_included": len(ai_context["evidence"]),
                "user_context": parameters["user_context"],
            },
        }

        sources = tuple(
            ArtifactSource(
                session_id=session_id,
                source_kind="session",
                source_reference={
                    "comparison_set_id": comparison.id,
                    "candidate_artifact_id": source.id,
                    "candidate_key": candidate_identity["candidate_key"],
                },
            )
            for session_id in comparison.session_ids
        )
        artifact = context.artifact_writer.write_json(
            filename="signal-hypothesis.json",
            artifact_type="signal_hypothesis",
            schema_version=SIGNAL_HYPOTHESIS_ARTIFACT_SCHEMA_VERSION,
            sources=sources,
            payload=payload,
            metadata={
                "comparison_set_id": comparison.id,
                "candidate_artifact_id": source.id,
                "candidate_key": candidate_identity["candidate_key"],
                "candidate_score": _ratio(candidate.get("candidate_score")),
                "strength": str(candidate.get("strength", "")),
                "ai_model": completion.model,
                "response_contract_version": 2,
                "response_sha256": response_sha256,
                "verified": False,
            },
        )
        context.progress.report(4, 4, "saved validated non-authoritative Signal Hypothesis artifact")
        return artifact


def _ai_context(
    artifact: ArtifactSnapshot,
    candidate: Mapping[str, Any],
    *,
    maximum_evidence_events: int,
    user_context: str,
) -> dict[str, Any]:
    evidence_value = candidate.get("evidence")
    evidence_rows = (
        [item for item in evidence_value if isinstance(item, Mapping)]
        if isinstance(evidence_value, (list, tuple))
        else []
    )
    evidence = [_compact_evidence(item) for item in evidence_rows[:maximum_evidence_events]]
    return {
        "task": "Propose a testable CAN signal hypothesis; do not claim confirmation.",
        "response_contract": {
            "version": 2,
            "all_fields_required": True,
            "nonempty_fields": ["name", "physical_meaning", "rationale"],
            "nonempty_arrays": ["next_experiments", "warnings"],
            "unknown_meaning_fallback": "unknown_bit_state_candidate",
        },
        "candidate_artifact": {
            "artifact_id": artifact.id,
            "sha256": artifact.sha256,
        },
        "candidate": {
            **_candidate_identity(candidate),
            "rank": _integer(candidate.get("rank")),
            "strength": str(candidate.get("strength", "")),
            "candidate_score": _ratio(candidate.get("candidate_score")),
            "support_count": _integer(candidate.get("support_count")),
            "best_support": _json_value(candidate.get("best_support")),
            "activity_validation": _json_value(candidate.get("activity_validation")),
        },
        "evidence": evidence,
        "operator_context": user_context or None,
    }


def _compact_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    marker = _mapping(value.get("marker"))
    before = _mapping(value.get("before"))
    after = _mapping(value.get("after"))
    return {
        "group": str(value.get("group", "")),
        "changed": bool(value.get("changed", False)),
        "session_id": str(value.get("session_id", "")),
        "session_name": str(value.get("session_name", "")),
        "marker": {
            "name": str(marker.get("name", "")),
            "note": str(marker.get("note", "")),
        },
        "before_state": _integer(value.get("before_state")),
        "after_state": _integer(value.get("after_state")),
        "delay_ns": _number_or_none(value.get("delay_ns")),
        "before": {
            "source_row": _integer(before.get("source_row"), default=-1),
            "payload_hex": str(before.get("payload_hex", "")),
        },
        "after": {
            "source_row": _integer(after.get("source_row"), default=-1),
            "payload_hex": str(after.get("payload_hex", "")),
        },
    }


def _validate_candidate_artifact(
    artifact: ArtifactSnapshot,
    comparison_set_id: str,
    comparison_session_ids: Sequence[str],
) -> None:
    if artifact.artifact_type != "signal_candidates":
        raise ValueError(f"artifact {artifact.id} is not signal_candidates")
    if artifact.schema_version != 1:
        raise ValueError(f"unsupported Signal Candidates schema {artifact.schema_version}")
    payload = artifact.payload
    if payload.get("schema") != "crt.signal_candidates":
        raise ValueError("unexpected Signal Candidates payload schema")
    comparison = _mapping(payload.get("comparison_set"))
    if str(comparison.get("id", "")) != comparison_set_id:
        raise ValueError("Signal Candidates artifact belongs to another comparison set")
    sessions = tuple(str(item) for item in comparison.get("session_ids", ()))
    if sessions and set(sessions) != set(comparison_session_ids):
        raise ValueError("Signal Candidates artifact has incompatible session set")


def _find_candidate(payload: Mapping[str, Any], candidate_key: str) -> Mapping[str, Any]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, (list, tuple)):
        raise ValueError("Signal Candidates artifact has no candidates")
    for candidate in candidates:
        if isinstance(candidate, Mapping) and str(candidate.get("candidate_key", "")) == candidate_key:
            return candidate
    raise ValueError(f"candidate not found in artifact: {candidate_key}")


def _candidate_identity(candidate: Mapping[str, Any]) -> dict[str, Any]:
    candidate_key = str(candidate.get("candidate_key", "")).strip()
    message_key = str(candidate.get("message_key", "")).strip()
    if not candidate_key or not message_key:
        raise ValueError("candidate identity is incomplete")
    return {
        "candidate_key": candidate_key,
        "message_key": message_key,
        "channel": _integer(candidate.get("channel")),
        "arbitration_id": _integer(candidate.get("arbitration_id")),
        "arbitration_id_hex": str(candidate.get("arbitration_id_hex", "")),
        "is_extended_id": bool(candidate.get("is_extended_id", False)),
        "frame_kind": str(candidate.get("frame_kind", "data")),
        "byte_index": _integer(candidate.get("byte_index"), default=-1),
        "bit_index": _integer(candidate.get("bit_index"), default=-1),
    }


def _normalize_hypothesis(value: Mapping[str, Any]) -> dict[str, Any]:
    missing = sorted(_REQUIRED_HYPOTHESIS_KEYS - set(value))
    if missing:
        raise LocalAIError(
            "AI hypothesis is missing required fields: " + ", ".join(missing)
        )

    name = _strict_text(value["name"], "name", 120, allow_empty=False)
    physical_meaning = _strict_text(
        value["physical_meaning"], "physical_meaning", 600, allow_empty=False
    )
    unit = _strict_optional_text(value["unit"], "unit", 60)
    scale = _strict_number_or_none(value["scale"], "scale")
    offset = _strict_number_or_none(value["offset"], "offset")
    confidence = _strict_confidence(value["confidence"])
    rationale = _strict_text(value["rationale"], "rationale", 1200, allow_empty=False)
    next_experiments = _strict_string_list(
        value["next_experiments"],
        "next_experiments",
        maximum=5,
        limit=400,
        require_nonempty=True,
    )
    warnings = _strict_string_list(
        value["warnings"],
        "warnings",
        maximum=5,
        limit=400,
        require_nonempty=True,
    )

    return {
        "name": name,
        "physical_meaning": physical_meaning,
        "unit": unit,
        "scale": scale,
        "offset": offset,
        "confidence": confidence,
        "rationale": rationale,
        "next_experiments": next_experiments,
        "warnings": warnings,
    }


def _parameters(values: Mapping[str, Any]) -> dict[str, Any]:
    artifact_id = str(values.get("candidate_artifact_id", "")).strip()
    candidate_key = str(values.get("candidate_key", "")).strip()
    if not artifact_id:
        raise ValueError("candidate_artifact_id is required")
    if not candidate_key:
        raise ValueError("candidate_key is required")
    maximum_evidence = int(values.get("maximum_evidence_events", _DEFAULT_MAXIMUM_EVIDENCE_EVENTS))
    if not 1 <= maximum_evidence <= _MAXIMUM_EVIDENCE_EVENTS_LIMIT:
        raise ValueError(
            f"maximum_evidence_events must be between 1 and {_MAXIMUM_EVIDENCE_EVENTS_LIMIT}"
        )
    return {
        "candidate_artifact_id": artifact_id,
        "candidate_key": candidate_key,
        "maximum_evidence_events": maximum_evidence,
        "user_context": _text(values.get("user_context", ""), 1000),
    }


def _comparison_input(context: AnalysisContext):
    if context.comparison is None:
        raise ValueError("Signal Hypothesis requires comparison context")
    inputs = [item for item in context.inputs if item.kind == "comparison_set"]
    if len(inputs) != 1 or inputs[0].source_id != context.comparison.id:
        raise ValueError("Signal Hypothesis requires exactly one matching comparison_set input")
    return inputs[0], context.comparison


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _strict_text(value: object, field: str, limit: int, *, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise LocalAIError(f"AI hypothesis field {field} must be a string")
    text = value.strip()[:limit]
    if not allow_empty and not text:
        raise LocalAIError(f"AI hypothesis field {field} cannot be empty")
    return text


def _strict_optional_text(value: object, field: str, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LocalAIError(f"AI hypothesis field {field} must be a string or null")
    text = value.strip()[:limit]
    return text or None


def _strict_number_or_none(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LocalAIError(f"AI hypothesis field {field} must be a number or null")
    number = float(value)
    if not math.isfinite(number):
        raise LocalAIError(f"AI hypothesis field {field} must be finite")
    return number


def _strict_confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LocalAIError("AI hypothesis field confidence must be a number from 0 to 1")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise LocalAIError("AI hypothesis field confidence must be between 0 and 1")
    return round(number, 6)


def _strict_string_list(
    value: object,
    field: str,
    *,
    maximum: int,
    limit: int,
    require_nonempty: bool,
) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise LocalAIError(f"AI hypothesis field {field} must be an array of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise LocalAIError(f"AI hypothesis field {field} must contain only strings")
        text = item.strip()[:limit]
        if text:
            result.append(text)
        if len(result) >= maximum:
            break
    if require_nonempty and not result:
        raise LocalAIError(f"AI hypothesis field {field} must contain at least one item")
    return result


def _response_excerpt(content: str, *, limit: int = 1200) -> str:
    compact = " ".join(str(content).strip().split())
    if len(compact) > limit:
        compact = compact[:limit] + "…"
    return json.dumps(compact, ensure_ascii=False)


def _integer(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number_or_none(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio(value: object) -> float:
    number = _number_or_none(value)
    if number is None:
        return 0.0
    return round(max(0.0, min(1.0, number)), 6)


__all__ = [
    "SIGNAL_HYPOTHESIS_ALGORITHM_VERSION",
    "SIGNAL_HYPOTHESIS_ARTIFACT_SCHEMA_VERSION",
    "SIGNAL_HYPOTHESIS_PROVIDER_ID",
    "SIGNAL_HYPOTHESIS_PROVIDER_VERSION",
    "SignalHypothesisAIProvider",
]
