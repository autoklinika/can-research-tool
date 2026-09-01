from __future__ import annotations

import json

import pytest

from app.extensions.builtin.signal_hypothesis_ai import (
    _normalize_hypothesis,
    _response_excerpt,
)
from app.local_ai import LocalAIError
from app.signal_hypothesis_service import (
    _repair_nonsemantic_response_omissions,
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


def test_response_excerpt_is_bounded_and_single_line() -> None:
    excerpt = _response_excerpt("{\n  \"status\": \"ok\"\n}" + " x" * 1000, limit=80)

    assert "\\n" not in excerpt
    assert len(excerpt) <= 90
    assert "status" in excerpt


def test_prompt_redacts_experiment_marker_and_session_labels_but_preserves_operator_context() -> None:
    raw = {
        "task": "hypothesis",
        "response_contract": {"version": 2},
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
                "target": {"event_count": 6, "changed_event_count": 6, "change_ratio": 1.0},
                "control": {"event_count": 4, "changed_event_count": 0, "change_ratio": 0.0},
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
    assert sanitized["response_contract"]["semantic_labels_redacted"] is True
    assert sanitized["response_contract"]["semantic_labels_source"] == "operator_context_only"
    assert sanitized["candidate"]["best_support"]["target"]["changed_event_count"] == 6
    assert sanitized["candidate"]["best_support"]["control"]["changed_event_count"] == 0


def test_safe_response_repair_adds_only_nonsemantic_nulls_and_conservative_missing_confidence() -> None:
    model_response = {
        "name": "unknown_bit_state_candidate",
        "physical_meaning": "Bit is correlated with the target experiment; physical meaning is unknown.",
        "rationale": "Target changed repeatedly while control did not.",
        "next_experiments": ["Repeat the inverse state and verify 1->0."],
        "warnings": ["Correlation is not semantic proof."],
    }

    repaired = json.loads(
        _repair_nonsemantic_response_omissions(json.dumps(model_response, ensure_ascii=False))
    )

    assert repaired["unit"] is None
    assert repaired["scale"] is None
    assert repaired["offset"] is None
    assert repaired["confidence"] == 0.0
    assert any("omitted confidence" in item for item in repaired["warnings"])
    normalized = _normalize_hypothesis(repaired)
    assert normalized["confidence"] == 0.0


def test_safe_response_repair_does_not_rescue_semantically_empty_json() -> None:
    assert _repair_nonsemantic_response_omissions("{}") == "{}"
