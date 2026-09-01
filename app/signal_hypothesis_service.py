from __future__ import annotations

import hashlib
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


_CONTEXT_POLICY = "label-redacted-v2-epistemic"
_RESPONSE_REPAIR_POLICY = "safe-nonsemantic-v3-pl"
_STRUCTURED_ARRAY_POLICY = "mapping-to-text-v1"
_NO_CONTEXT_POLICY = "neutral-semantic-fallback-v1"


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
        prompt_payload = _prompt_payload(sanitized_prompt)
        operator_context = _operator_context(prompt_payload)
        semantic_context_available = bool(operator_context)

        format_note = (
            "\nDla tego żądania nazwy eksperymentów, markerów i sesji zostały celowo "
            "usunięte, aby ograniczyć semantyczne zakotwiczenie modelu. Wnioskuj o znaczeniu "
            "wyłącznie wtedy, gdy operator_context jawnie wnosi taką wskazówkę, i nadal traktuj "
            "ją jako wskazówkę, nie dowód. Wszystkie pola opisowe odpowiedzi "
            "(physical_meaning, rationale, next_experiments, warnings) zapisz po polsku (pl-PL). "
            "confidence jest opcjonalne; jeżeli nie potrafisz uzasadnić wartości, pomiń je zamiast "
            "zgadywać. next_experiments i warnings mają być tablicami tekstów, nie obiektów."
        )
        if not semantic_context_available:
            format_note += (
                "\noperator_context jest pusty. W takim przypadku NIE przypisuj żadnego znaczenia "
                "domenowego ani fizycznego (np. EGR, wentylator, przekaźnik, temperatura, ciśnienie). "
                "Użyj name=unknown_bit_state_candidate i opisz wyłącznie nieznany stan binarny "
                "skorelowany z obserwowanym wzorcem target/control."
            )

        completion = self._inner.complete(
            system_prompt=str(system_prompt) + format_note,
            user_prompt=sanitized_prompt,
            cancellation=cancellation,
        )
        raw_content = completion.content
        repaired = _repair_nonsemantic_response_omissions(raw_content)
        shaped = _repair_structured_text_arrays(repaired)
        guarded = (
            _apply_no_context_semantic_guardrail(shaped, prompt_payload)
            if not semantic_context_available
            else shaped
        )

        usage = dict(completion.usage)
        usage["crt_context_policy"] = _CONTEXT_POLICY
        usage["crt_response_repair_policy"] = _RESPONSE_REPAIR_POLICY
        usage["crt_structured_array_policy"] = _STRUCTURED_ARRAY_POLICY
        usage["crt_no_context_policy"] = _NO_CONTEXT_POLICY
        usage["crt_semantic_context_available"] = semantic_context_available
        usage["crt_response_repaired"] = guarded != raw_content
        usage["crt_structured_arrays_repaired"] = shaped != repaired
        usage["crt_semantic_guardrail_applied"] = guarded != shaped
        usage["crt_raw_response_sha256"] = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()

        return LocalAICompletion(
            provider=completion.provider,
            model=completion.model,
            endpoint=completion.endpoint,
            content=guarded,
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


def _prompt_payload(user_prompt: str) -> dict[str, Any]:
    try:
        value = json.loads(str(user_prompt))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _operator_context(payload: Mapping[str, Any]) -> str:
    value = payload.get("operator_context")
    return str(value).strip() if value is not None else ""


def _repair_nonsemantic_response_omissions(content: str) -> str:
    """Repair only omissions that cannot create new physical meaning."""

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
                "Model nie podał confidence; CRT przypisał 0.0 zamiast wymyślać poziom pewności."
            )
            repaired["warnings"] = warnings
        changed = True

    if not changed:
        return content
    return json.dumps(repaired, ensure_ascii=False, separators=(",", ":"))


def _repair_structured_text_arrays(content: str) -> str:
    """Flatten model-produced text objects without inventing new semantics."""

    try:
        payload = extract_json_object(content)
    except Exception:
        return content

    repaired = dict(payload)
    changed = False
    for key in ("next_experiments", "warnings"):
        value = repaired.get(key)
        if not isinstance(value, list):
            continue
        items: list[object] = []
        for item in value:
            if isinstance(item, Mapping):
                text = _mapping_text(item)
                items.append(text if text else item)
                if text:
                    changed = True
            else:
                items.append(item)
        repaired[key] = items

    if not changed:
        return content
    return json.dumps(repaired, ensure_ascii=False, separators=(",", ":"))


def _mapping_text(value: Mapping[str, Any]) -> str:
    preferred = (
        "name",
        "title",
        "description",
        "procedure",
        "steps",
        "expected_result",
        "expected",
        "reason",
        "warning",
        "text",
        "details",
    )
    parts: list[str] = []
    seen: set[str] = set()

    def add(item: object) -> None:
        if isinstance(item, str):
            text = item.strip()
            if text and text not in seen:
                seen.add(text)
                parts.append(text)
        elif isinstance(item, list):
            texts = [str(entry).strip() for entry in item if isinstance(entry, str) and str(entry).strip()]
            if texts:
                add("; ".join(texts))

    for key in preferred:
        if key in value:
            add(value.get(key))
    if not parts:
        for item in value.values():
            add(item)
    return " — ".join(parts)


def _apply_no_context_semantic_guardrail(
    content: str,
    prompt_payload: Mapping[str, Any],
) -> str:
    """Replace unsupported domain semantics with an evidence-only neutral hypothesis.

    With no operator_context CRT has structural/correlation evidence but no deliberate
    semantic evidence. A domain-specific physical interpretation from the LLM is
    therefore not admissible as a Signal Hypothesis artifact.
    """

    try:
        payload = extract_json_object(content)
    except Exception:
        return content

    semantic_core = ("name", "physical_meaning", "rationale", "next_experiments", "warnings")
    if not all(key in payload for key in semantic_core):
        return content

    neutral = dict(payload)
    neutral["name"] = "unknown_bit_state_candidate"
    neutral["physical_meaning"] = (
        "Nieznany stan binarny skorelowany z obserwowanym wzorcem target/control; "
        "na podstawie dostępnych danych nie można przypisać mu znaczenia fizycznego."
    )
    neutral["unit"] = None
    neutral["scale"] = None
    neutral["offset"] = None
    neutral["confidence"] = 0.0
    neutral["rationale"] = _neutral_rationale(prompt_payload)
    neutral["next_experiments"] = _neutral_next_experiments(prompt_payload)
    neutral["warnings"] = [
        "Brak kontekstu operatora; CRT celowo zneutralizował domenową interpretację modelu.",
        "Silna korelacja deterministyczna nie jest dowodem znaczenia fizycznego sygnału.",
    ]
    return json.dumps(neutral, ensure_ascii=False, separators=(",", ":"))


def _neutral_rationale(prompt_payload: Mapping[str, Any]) -> str:
    candidate = prompt_payload.get("candidate")
    candidate_map = candidate if isinstance(candidate, Mapping) else {}
    support = candidate_map.get("best_support")
    support_map = support if isinstance(support, Mapping) else {}
    target = support_map.get("target")
    target_map = target if isinstance(target, Mapping) else {}
    control = support_map.get("control")
    control_map = control if isinstance(control, Mapping) else {}
    direction = support_map.get("direction")
    direction_map = direction if isinstance(direction, Mapping) else {}
    timing = support_map.get("timing")
    timing_map = timing if isinstance(timing, Mapping) else {}

    facts: list[str] = []
    score = candidate_map.get("candidate_score")
    strength = str(candidate_map.get("strength", "")).strip()
    if isinstance(score, (int, float)):
        text = f"Deterministyczny score kandydata wynosi {float(score):.3f}"
        if strength:
            text += f" (klasa {strength})"
        facts.append(text + ".")

    target_changed = target_map.get("changed_event_count")
    target_events = target_map.get("eligible_event_count", target_map.get("event_count"))
    control_changed = control_map.get("changed_event_count")
    control_events = control_map.get("eligible_event_count", control_map.get("event_count"))
    if all(isinstance(value, (int, float)) for value in (target_changed, target_events)):
        facts.append(
            f"Zmiana wystąpiła w {int(target_changed)}/{int(target_events)} kwalifikowanych zdarzeniach target."
        )
    if all(isinstance(value, (int, float)) for value in (control_changed, control_events)):
        facts.append(
            f"W kontroli zmiana wystąpiła w {int(control_changed)}/{int(control_events)} kwalifikowanych zdarzeniach."
        )

    dominant = str(direction_map.get("dominant", "")).strip()
    if dominant:
        facts.append(f"Dominujący kierunek zmiany to {dominant}.")

    mean_delay_ns = timing_map.get("mean_delay_ns")
    if isinstance(mean_delay_ns, (int, float)):
        facts.append(f"Średnie opóźnienie względem zdarzenia wynosi około {float(mean_delay_ns) / 1_000_000:.1f} ms.")

    facts.append(
        "Dane wspierają korelację i powtarzalność kandydata, ale bez kontekstu semantycznego nie identyfikują funkcji fizycznej."
    )
    return " ".join(facts)


def _neutral_next_experiments(prompt_payload: Mapping[str, Any]) -> list[str]:
    candidate = prompt_payload.get("candidate")
    candidate_map = candidate if isinstance(candidate, Mapping) else {}
    support = candidate_map.get("best_support")
    support_map = support if isinstance(support, Mapping) else {}
    direction = support_map.get("direction")
    direction_map = direction if isinstance(direction, Mapping) else {}
    dominant = str(direction_map.get("dominant", "")).strip()

    if dominant == "0->1":
        inverse = "1→0"
    elif dominant == "1->0":
        inverse = "0→1"
    else:
        inverse = "odwrotne"

    return [
        f"Powtórz eksperyment w przeciwnym stanie i sprawdź, czy kandydat wykona przejście {inverse}.",
        "Dodaj niezależny test kontrolny, który zmienia inny warunek przy niezmienionym badanym stanie, aby sprawdzić swoistość korelacji.",
    ]


__all__ = ["SignalHypothesisService"]
