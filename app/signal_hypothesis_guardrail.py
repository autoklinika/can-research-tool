from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .local_ai import extract_json_object


OPERATOR_CONTEXT_POLICY = "operator-context-domain-hint-only-v1"
_MAX_CONTEXT_SUMMARY = 180
_MAX_CONTEXT_CONFIDENCE = 0.35


def apply_operator_context_guardrail(
    content: str,
    prompt_payload: Mapping[str, Any],
) -> str:
    """Limit operator context to a domain hint, never a bit-semantic assertion.

    The LLM may use explicit operator context to propose verification experiments, but
    CRT itself owns the persisted semantic claim. This guardrail deterministically
    prevents the model from assigning a concrete physical function, command/feedback
    role, actuator type, threshold, default state, or meaning to binary states 0/1.
    """

    operator_context = _operator_context(prompt_payload)
    if not operator_context:
        return content

    try:
        payload = extract_json_object(content)
    except Exception:
        return content

    semantic_core = ("name", "physical_meaning", "rationale", "next_experiments", "warnings")
    if not all(key in payload for key in semantic_core):
        return content

    guarded = dict(payload)
    context_summary = _context_summary(operator_context)
    guarded["name"] = "operator_context_correlated_candidate"
    guarded["physical_meaning"] = (
        f"Kontekst operatora wskazuje obszar eksperymentu: \"{context_summary}\". "
        "Kandydat może być związany z tym obszarem, ale dostępne evidence nie pozwala "
        "określić funkcji bitu ani znaczenia stanów 0 i 1."
    )
    guarded["unit"] = None
    guarded["scale"] = None
    guarded["offset"] = None
    guarded["confidence"] = _bounded_confidence(payload.get("confidence"))
    guarded["rationale"] = _evidence_rationale(prompt_payload, context_summary)
    # Keep model-proposed verification experiments: this is the useful interpretive
    # part of AI. The semantic claim itself and the persisted warnings are deterministic.
    guarded["warnings"] = [
        "Kontekst operatora jest wskazówką semantyczną, a nie dowodem znaczenia sygnału.",
        "CRT nie przypisuje znaczenia stanom 0/1 ani roli komenda/pomiar bez osobnego evidence.",
        "Silna korelacja z eksperymentem nie potwierdza funkcji fizycznej kandydata.",
    ]
    return json.dumps(guarded, ensure_ascii=False, separators=(",", ":"))


def _operator_context(payload: Mapping[str, Any]) -> str:
    value = payload.get("operator_context")
    return str(value).strip() if value is not None else ""


def _context_summary(value: str) -> str:
    text = " ".join(str(value).split()).strip()
    if not text:
        return "brak opisu"
    # Preserve only the first declarative sentence as the domain hint. Later text may
    # contain instructions to the model and must not become persisted evidence.
    for separator in (".", "!", "?"):
        position = text.find(separator)
        if 0 <= position < _MAX_CONTEXT_SUMMARY:
            text = text[: position + 1]
            break
    return text[:_MAX_CONTEXT_SUMMARY].strip()


def _bounded_confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    number = max(0.0, min(float(value), 1.0))
    return min(number, _MAX_CONTEXT_CONFIDENCE)


def _evidence_rationale(
    prompt_payload: Mapping[str, Any],
    context_summary: str,
) -> str:
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
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        text = f"Deterministyczny score kandydata wynosi {float(score):.3f}"
        if strength:
            text += f" (klasa {strength})"
        facts.append(text + ".")

    target_changed = target_map.get("changed_event_count")
    target_events = target_map.get("eligible_event_count", target_map.get("event_count"))
    control_changed = control_map.get("changed_event_count")
    control_events = control_map.get("eligible_event_count", control_map.get("event_count"))
    if _numbers(target_changed, target_events):
        facts.append(
            f"Zmiana wystąpiła w {int(target_changed)}/{int(target_events)} kwalifikowanych zdarzeniach target."
        )
    if _numbers(control_changed, control_events):
        facts.append(
            f"W kontroli zmiana wystąpiła w {int(control_changed)}/{int(control_events)} kwalifikowanych zdarzeniach."
        )

    dominant = str(direction_map.get("dominant", "")).strip()
    if dominant:
        facts.append(f"Dominujący kierunek obserwowanej zmiany to {dominant}.")

    mean_delay_ns = timing_map.get("mean_delay_ns")
    if isinstance(mean_delay_ns, (int, float)) and not isinstance(mean_delay_ns, bool):
        facts.append(
            f"Średnie opóźnienie względem zdarzenia wynosi około {float(mean_delay_ns) / 1_000_000:.1f} ms."
        )

    facts.append(f"Operator podał kontekst eksperymentu: \"{context_summary}\"")
    facts.append(
        "Te dane wspierają związek z opisanym eksperymentem, ale nie identyfikują funkcji bitu "
        "ani semantyki jego stanów."
    )
    return " ".join(facts)


def _numbers(*values: object) -> bool:
    return all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in values
    )


__all__ = ["OPERATOR_CONTEXT_POLICY", "apply_operator_context_guardrail"]
