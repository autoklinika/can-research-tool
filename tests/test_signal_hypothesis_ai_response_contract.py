from __future__ import annotations

import json

import pytest

from app.extensions.builtin.signal_hypothesis_ai import (
    _normalize_hypothesis,
    _response_excerpt,
)
from app.local_ai import LocalAIError
from app.signal_hypothesis_service import (
    _apply_no_context_semantic_guardrail,
    _repair_nonsemantic_response_omissions,
    _repair_structured_text_arrays,
    _sanitize_signal_hypothesis_prompt,
)


def _valid_response() -> dict[str, object]:
    return {
        "name": "unknown_bit_state_candidate",
        "physical_meaning": "Nieznany binarny stan skorelowany z eksperymentem; znaczenie fizyczne nie jest potwierdzone.",
        "unit": None,
        "scale": None,
        "offset": None,
        "confidence": 0.35,
        "rationale": "Kandydat zmienia się dla targetu i nie zmienia się dla kontroli; dane potwierdzają korelację, ale nie semantykę sygnału.",
        "next_experiments": [
            "Powtórz eksperyment w przeciwnym stanie i sprawdź przejście 1->0."
        ],
        "warnings": ["Etykieta eksperymentu nie jest dowodem znaczenia sygnału."],
    }


def test_rejects_json_object_without_hypothesis_contract() -> None:
    with pytest.raises(LocalAIError, match="missing required fields"):
        _normalize_hypothesis({"status": "ok"})


def test_rejects_empty_object_from_model() -> None:
    with pytest.raises(LocalAIError, match="missing required fields"):
        _normalize_hypothesis({})


def test_rejects_empty_semantic_hypothesis() -> None:
    payload = _valid_response()
    payload["physical_meaning"] = ""
    payload["rationale"] = ""
    payload["next_experiments"] = []

    with pytest.raises(LocalAIError, match="physical_meaning"):
        _normalize_hypothesis(payload)


def test_rejects_empty_name_instead_of_saving_bez_nazwy() -> None:
    payload = _valid_response()
    payload["name"] = ""

    with pytest.raises(LocalAIError, match="name cannot be empty"):
        _normalize_hypothesis(payload)


def test_rejects_missing_verification_experiment() -> None:
    payload = _valid_response()
    payload["next_experiments"] = []

    with pytest.raises(LocalAIError, match="next_experiments.*at least one item"):
        _normalize_hypothesis(payload)


def test_rejects_missing_warning() -> None:
    payload = _valid_response()
    payload["warnings"] = []

    with pytest.raises(LocalAIError, match="warnings.*at least one item"):
        _normalize_hypothesis(payload)


def test_rejects_confidence_outside_contract_instead_of_clamping() -> None:
    payload = _valid_response()
    payload["confidence"] = 1.7

    with pytest.raises(LocalAIError, match="confidence.*between 0 and 1"):
        _normalize_hypothesis(payload)


def test_rejects_wrong_array_types() -> None:
    payload = _valid_response()
    payload["next_experiments"] = "repeat test"

    with pytest.raises(LocalAIError, match="next_experiments.*array of strings"):
        _normalize_hypothesis(payload)


def test_accepts_uncertain_but_actionable_hypothesis() -> None:
    normalized = _normalize_hypothesis(_valid_response())

    assert normalized["name"] == "unknown_bit_state_candidate"
    assert normalized["confidence"] == pytest.approx(0.35)
    assert normalized["unit"] is None
    assert normalized["scale"] is None
    assert normalized["offset"] is None
    assert len(normalized["next_experiments"]) == 1
    assert len(normalized["warnings"]) == 1


def test_accepts_missing_nonsemantic_optional_fields_without_inventing_confidence() -> None:
    payload = _valid_response()
    for key in ("unit", "scale", "offset", "confidence"):
        payload.pop(key)

    normalized = _normalize_hypothesis(payload)

    assert normalized["unit"] is None
    assert normalized["scale"] is None
    assert normalized["offset"] is None
    assert normalized["confidence"] == 0.0
    assert any("nie podał confidence" in item for item in normalized["warnings"])


def test_response_excerpt_is_bounded_and_single_line() -> None:
    excerpt = _response_excerpt("{\n  \"status\": \"ok\"\n}" + " x" * 1000, limit=80)

    assert "\\n" not in excerpt
    assert len(excerpt) <= 90
    assert "status" in excerpt


def test_prompt_redacts_experiment_marker_and_session_labels_but_preserves_operator_context() -> None:
    raw = {
        "task": "hypothesis",
        "response_contract": {"version": 2, "language": "pl-PL"},
        "candidate": {
            "candidate_key": "0:STD:321:data:B0.2",
            "candidate_score": 1.0,
            "best_support": {
                "experiment": {
                    "target": {"name": "TEST_EGR", "label": "EGR disconnected", "selector": "preset:egr"},
                    "control": {"name": "CONTROL", "label": "CONTROL"},
                    "pre_window_ms": 30,
                    "post_window_ms": 50,
                },
                "score": 1.0,
                "target": {"event_count": 6, "eligible_event_count": 6, "changed_event_count": 6, "change_ratio": 1.0},
                "control": {"event_count": 4, "eligible_event_count": 4, "changed_event_count": 0, "change_ratio": 0.0},
                "direction": {"dominant": "0->1", "consistency_ratio": 1.0},
                "timing": {"mean_delay_ns": 70_000_000.0},
                "evidence_event_count": 10,
                "evidence_truncated": False,
            },
            "activity_validation": {
                "status": "consistent",
                "session_count": 2,
                "artifacts": [{"session_name": "EGR target run"}],
            },
        },
        "evidence": [
            {
                "group": "target",
                "changed": True,
                "session_id": "opaque-id",
                "session_name": "TEST_EGR session",
                "marker": {"name": "TEST_EGR", "note": "physical EGR disconnect"},
                "before_state": 0,
                "after_state": 1,
                "delay_ns": 70_000_000.0,
                "before": {"source_row": 10, "payload_hex": "00"},
                "after": {"source_row": 11, "payload_hex": "04"},
            }
        ],
        "operator_context": "operator explicitly says EGR here",
    }

    sanitized = json.loads(_sanitize_signal_hypothesis_prompt(json.dumps(raw)))
    machine_context = json.dumps(
        {"candidate": sanitized["candidate"], "evidence": sanitized["evidence"]},
        ensure_ascii=False,
    )

    assert "TEST_EGR" not in machine_context
    assert "EGR disconnected" not in machine_context
    assert "physical EGR disconnect" not in machine_context
    assert "session_name" not in machine_context
    assert "marker" not in sanitized["evidence"][0]
    assert sanitized["operator_context"] == "operator explicitly says EGR here"
    assert sanitized["response_contract"]["language"] == "pl-PL"
    assert sanitized["response_contract"]["semantic_labels_redacted"] is True
    assert sanitized["response_contract"]["semantic_labels_source"] == "operator_context_only"
    assert sanitized["candidate"]["best_support"]["target"]["changed_event_count"] == 6
    assert sanitized["candidate"]["best_support"]["control"]["changed_event_count"] == 0


def test_safe_response_repair_adds_only_nonsemantic_nulls_and_conservative_missing_confidence() -> None:
    model_response = {
        "name": "unknown_bit_state_candidate",
        "physical_meaning": "Bit jest skorelowany z eksperymentem target; znaczenie fizyczne pozostaje nieznane.",
        "rationale": "Target zmieniał się wielokrotnie, podczas gdy kontrola pozostawała stabilna.",
        "next_experiments": ["Powtórz stan przeciwny i zweryfikuj przejście 1->0."],
        "warnings": ["Korelacja nie jest dowodem semantycznym."],
    }

    repaired = json.loads(
        _repair_nonsemantic_response_omissions(json.dumps(model_response, ensure_ascii=False))
    )

    assert repaired["unit"] is None
    assert repaired["scale"] is None
    assert repaired["offset"] is None
    assert repaired["confidence"] == 0.0
    assert any("nie podał confidence" in item for item in repaired["warnings"])
    normalized = _normalize_hypothesis(repaired)
    assert normalized["confidence"] == 0.0


def test_safe_response_repair_does_not_rescue_semantically_empty_json() -> None:
    assert _repair_nonsemantic_response_omissions("{}") == "{}"


def test_structured_next_experiments_are_flattened_without_inventing_text() -> None:
    payload = _valid_response()
    payload["next_experiments"] = [
        {
            "name": "Test reakcji na zmianę stanu",
            "description": "Powtórz eksperyment i sprawdź przejście odwrotne.",
        }
    ]

    repaired = json.loads(_repair_structured_text_arrays(json.dumps(payload, ensure_ascii=False)))

    assert repaired["next_experiments"] == [
        "Test reakcji na zmianę stanu — Powtórz eksperyment i sprawdź przejście odwrotne."
    ]
    normalized = _normalize_hypothesis(repaired)
    assert len(normalized["next_experiments"]) == 1


def test_no_context_guardrail_neutralizes_domain_hallucination_from_real_test_shape() -> None:
    hallucination = {
        "name": "Sygnał sterujący przekaźnikiem chłodzenia silnika",
        "physical_meaning": "Stan przekaźnika wentylatora chłodzącego aktywowany po przekroczeniu 95 C.",
        "unit": None,
        "scale": None,
        "offset": None,
        "confidence": 0.95,
        "rationale": "Wysoka temperatura powoduje aktywację wentylatora.",
        "next_experiments": [
            {
                "name": "Test obciążenia termicznego",
                "description": "Podgrzej silnik i obserwuj wentylator.",
            }
        ],
        "warnings": ["Sprawdź przekaźnik."],
    }
    prompt_payload = {
        "candidate": {
            "candidate_score": 1.0,
            "strength": "strong",
            "best_support": {
                "target": {
                    "event_count": 6,
                    "eligible_event_count": 6,
                    "changed_event_count": 6,
                },
                "control": {
                    "event_count": 4,
                    "eligible_event_count": 4,
                    "changed_event_count": 0,
                },
                "direction": {"dominant": "0->1"},
                "timing": {"mean_delay_ns": 70_000_000.0},
            },
        },
        "operator_context": None,
    }

    shaped = _repair_structured_text_arrays(json.dumps(hallucination, ensure_ascii=False))
    guarded = json.loads(_apply_no_context_semantic_guardrail(shaped, prompt_payload))
    rendered = json.dumps(guarded, ensure_ascii=False).lower()

    assert guarded["name"] == "unknown_bit_state_candidate"
    assert guarded["confidence"] == 0.0
    assert guarded["unit"] is None
    assert guarded["scale"] is None
    assert guarded["offset"] is None
    assert "6/6" in guarded["rationale"]
    assert "0/4" in guarded["rationale"]
    assert "70.0 ms" in guarded["rationale"]
    assert "1→0" in guarded["next_experiments"][0]
    assert "chłod" not in rendered
    assert "wentyl" not in rendered
    assert "95" not in rendered
    assert any("Brak kontekstu operatora" in item for item in guarded["warnings"])
    normalized = _normalize_hypothesis(guarded)
    assert normalized["name"] == "unknown_bit_state_candidate"
