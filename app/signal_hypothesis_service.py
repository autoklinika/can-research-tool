from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .artifact_catalog import ArtifactCatalog
from .comparison_analysis_service import (
    ComparisonAnalysisExecutionResult,
    ComparisonAnalysisService,
)
from .domain import Artifact
from .extensions import ExtensionRegistry
from .extensions.builtin import (
    register_builtin_comparison_extensions,
    register_builtin_extensions,
)
from .extensions.builtin.signal_hypothesis_ai import (
    SIGNAL_HYPOTHESIS_ARTIFACT_SCHEMA_VERSION,
    SIGNAL_HYPOTHESIS_PROVIDER_ID,
    SignalHypothesisAIProvider,
)
from .local_ai import (
    LocalAIClient,
    LocalAICompletion,
    LocalAIConfig,
    OpenAICompatibleLocalClient,
    extract_json_object,
)
from .project import CrtProject


_CONTEXT_POLICY = "label-redacted-v1"
_RESPONSE_REPAIR_POLICY = "safe-nonsemantic-v1"


class _SignalHypothesisAIClient:
    """Feature-local wrapper that removes experiment-label bias before inference.

    Deterministic evidence stays unchanged in CRT artifacts. Only the bounded prompt
    sent to the optional LLM is sanitized. Explicit operator_context is preserved,
    because that field is the deliberate channel for semantic hints.
    """

    def __init__(self, inner: LocalAIClient) -> None:
        self._inner = inner

    @property
    def config(self) -> LocalAIConfig:
        return self._inner.config

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        cancellation=None,
    ) -> LocalAICompletion:
        sanitized_prompt = _sanitize_signal_hypothesis_prompt(user_prompt)
        format_note = (
            "\nFor this request, experiment/marker/session labels were intentionally "
            "redacted to prevent semantic anchoring. Infer semantics only when operator_context "
            "explicitly supplies them. confidence is mandatory and must be numeric 0..1; use a "
            "low value when uncertain."
        )
        completion = self._inner.complete(
            system_prompt=str(system_prompt) + format_note,
            user_prompt=sanitized_prompt,
            cancellation=cancellation,
        )
        repaired = _repair_nonsemantic_response_omissions(completion.content)
        usage = dict(completion.usage)
        usage["crt_context_policy"] = _CONTEXT_POLICY
        usage["crt_response_repair_policy"] = _RESPONSE_REPAIR_POLICY
        usage["crt_response_repaired"] = repaired != completion.content
        return LocalAICompletion(
            provider=completion.provider,
            model=completion.model,
            endpoint=completion.endpoint,
            content=repaired,
            latency_ms=completion.latency_ms,
            usage=usage,
        )


class SignalHypothesisService:
    """Offline-safe catalog plus optional local-AI hypothesis execution."""

    def __init__(
        self,
        project: CrtProject,
        *,
        ai_client: LocalAIClient | None = None,
    ) -> None:
        self.project = project
        self.ai_client = ai_client
        self.artifacts = ArtifactCatalog(project)

    @classmethod
    def from_config(
        cls,
        project: CrtProject,
        config: LocalAIConfig,
    ) -> "SignalHypothesisService":
        return cls(project, ai_client=OpenAICompatibleLocalClient(config))

    def list_candidate_artifacts(self, comparison_set_id: str) -> tuple[Artifact, ...]:
        return tuple(
            artifact
            for artifact in self.artifacts.list_for_comparison_set(comparison_set_id)
            if artifact.artifact_type == "signal_candidates"
        )

    def candidate_rows(self, artifact: Artifact) -> tuple[dict[str, Any], ...]:
        payload = self.artifacts.read_json(artifact)
        if payload.get("schema") != "crt.signal_candidates":
            raise ValueError("wybrany artefakt nie jest Signal Candidates")
        rows = payload.get("candidates")
        if not isinstance(rows, list):
            return ()
        return tuple(dict(item) for item in rows if isinstance(item, Mapping))

    def run(
        self,
        comparison_set_id: str,
        *,
        candidate_artifact_id: str,
        candidate_key: str,
        user_context: str = "",
        maximum_evidence_events: int = 8,
        cancellation=None,
        progress_callback=None,
    ) -> ComparisonAnalysisExecutionResult:
        if self.ai_client is None:
            raise ValueError("lokalne AI nie jest skonfigurowane")
        registry = ExtensionRegistry(passive_only=True, ai_enabled=True)
        register_builtin_extensions(registry)
        register_builtin_comparison_extensions(registry)
        registry.register(SignalHypothesisAIProvider())
        analysis = ComparisonAnalysisService(
            self.project,
            registry=registry,
            ai_client=_SignalHypothesisAIClient(self.ai_client),
        )
        return analysis.run(
            SIGNAL_HYPOTHESIS_PROVIDER_ID,
            comparison_set_id,
            parameters={
                "candidate_artifact_id": candidate_artifact_id,
                "candidate_key": candidate_key,
                "user_context": user_context,
                "maximum_evidence_events": int(maximum_evidence_events),
            },
            cancellation=cancellation,
            progress_callback=progress_callback,
        )

    def list_hypothesis_artifacts(self, comparison_set_id: str) -> tuple[Artifact, ...]:
        return tuple(
            artifact
            for artifact in self.artifacts.list_for_comparison_set(comparison_set_id)
            if artifact.artifact_type == "signal_hypothesis"
            and artifact.schema_version == SIGNAL_HYPOTHESIS_ARTIFACT_SCHEMA_VERSION
        )

    def legacy_hypothesis_count(self, comparison_set_id: str) -> int:
        return sum(
            1
            for artifact in self.artifacts.list_for_comparison_set(comparison_set_id)
            if artifact.artifact_type == "signal_hypothesis"
            and artifact.schema_version != SIGNAL_HYPOTHESIS_ARTIFACT_SCHEMA_VERSION
        )

    def read_hypothesis(self, artifact: Artifact) -> dict[str, Any]:
        if artifact.artifact_type != "signal_hypothesis":
            raise ValueError("wybrany artefakt nie jest Signal Hypothesis")
        if artifact.schema_version != SIGNAL_HYPOTHESIS_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                "starszy artefakt Signal Hypothesis ma nieaktualny kontrakt odpowiedzi AI"
            )
        payload = self.artifacts.read_json(artifact)
        if payload.get("schema") != "crt.signal_hypothesis":
            raise ValueError("nieoczekiwany schemat Signal Hypothesis")
        if payload.get("schema_version") != SIGNAL_HYPOTHESIS_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("niespójna wersja schematu Signal Hypothesis")
        return dict(payload)


def _sanitize_signal_hypothesis_prompt(user_prompt: str) -> str:
    try:
        payload = json.loads(str(user_prompt))
    except (json.JSONDecodeError, TypeError, ValueError):
        return str(user_prompt)
    if not isinstance(payload, dict):
        return str(user_prompt)

    candidate = payload.get("candidate")
    if isinstance(candidate, Mapping):
        candidate_copy = dict(candidate)
        candidate_copy["best_support"] = _sanitize_best_support(candidate.get("best_support"))
        candidate_copy["activity_validation"] = _sanitize_activity(candidate.get("activity_validation"))
        payload["candidate"] = candidate_copy

    evidence = payload.get("evidence")
    if isinstance(evidence, list):
        payload["evidence"] = [
            _sanitize_evidence(item) for item in evidence if isinstance(item, Mapping)
        ]

    response_contract = payload.get("response_contract")
    if isinstance(response_contract, Mapping):
        contract = dict(response_contract)
        contract["semantic_labels_redacted"] = True
        contract["semantic_labels_source"] = "operator_context_only"
        payload["response_contract"] = contract

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def _sanitize_best_support(value: object) -> dict[str, Any]:
    support = value if isinstance(value, Mapping) else {}
    return {
        "score": support.get("score"),
        "target": _pick_mapping(
            support.get("target"),
            "event_count",
            "eligible_event_count",
            "changed_event_count",
            "change_ratio",
        ),
        "control": _pick_mapping(
            support.get("control"),
            "event_count",
            "eligible_event_count",
            "changed_event_count",
            "change_ratio",
        ),
        "direction": _pick_mapping(
            support.get("direction"),
            "dominant",
            "consistency_ratio",
            "observed_change_count",
        ),
        "timing": _pick_mapping(
            support.get("timing"),
            "mean_delay_ns",
            "median_delay_ns",
            "min_delay_ns",
            "max_delay_ns",
        ),
        "evidence_event_count": support.get("evidence_event_count"),
        "evidence_truncated": support.get("evidence_truncated"),
    }


def _sanitize_activity(value: object) -> dict[str, Any]:
    return _pick_mapping(
        value,
        "status",
        "artifact_count",
        "session_count",
        "comparison_session_count",
        "coverage_ratio",
        "variable_observation_count",
        "constant_observation_count",
        "variable_ratio",
        "transition_count",
        "transition_opportunity_count",
        "transition_rate",
        "set_ratio",
    )


def _sanitize_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "group": value.get("group"),
        "changed": value.get("changed"),
        "before_state": value.get("before_state"),
        "after_state": value.get("after_state"),
        "delay_ns": value.get("delay_ns"),
        "before": _pick_mapping(value.get("before"), "source_row", "payload_hex"),
        "after": _pick_mapping(value.get("after"), "source_row", "payload_hex"),
    }


def _pick_mapping(value: object, *keys: str) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {key: source.get(key) for key in keys if key in source}


def _repair_nonsemantic_response_omissions(content: str) -> str:
    """Repair only omissions that cannot create new physical meaning.

    unit/scale/offset default to null. Missing AI self-confidence is conservatively
    set to 0.0 only when the response already contains the semantic core and a
    verification experiment; an explicit warning is appended. Empty/invalid
    semantic hypotheses still flow unchanged to the strict provider validator.
    """

    try:
        payload = extract_json_object(content)
    except Exception:
        return content

    semantic_core = ("name", "physical_meaning", "rationale", "next_experiments", "warnings")
    if not all(key in payload for key in semantic_core):
        return content

    repaired = dict(payload)
    changed = False
    for key in ("unit", "scale", "offset"):
        if key not in repaired:
            repaired[key] = None
            changed = True

    if "confidence" not in repaired:
        repaired["confidence"] = 0.0
        warnings = repaired.get("warnings")
        if isinstance(warnings, list):
            warnings = list(warnings)
            warnings.append(
                "AI omitted confidence; CRT assigned 0.0 rather than inventing confidence."
            )
            repaired["warnings"] = warnings
        changed = True

    if not changed:
        return content
    return json.dumps(repaired, ensure_ascii=False, separators=(",", ":"))


__all__ = ["SignalHypothesisService"]
