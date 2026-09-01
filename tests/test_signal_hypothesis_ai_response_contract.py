from __future__ import annotations

import pytest

from app.extensions.builtin.signal_hypothesis_ai import (
    _normalize_hypothesis,
    _response_excerpt,
)
from app.local_ai import LocalAIError


def _valid_response() -> dict[str, object]:
    return {
        "name": "unknown_bit_state_candidate",
        "physical_meaning": "Nieznany binarny stan skorelowany z eksperymentem TEST_EGR; znaczenie fizyczne nie jest potwierdzone.",
        "unit": None,
        "scale": None,
        "offset": None,
        "confidence": 0.35,
        "rationale": "Kandydat zmienia się dla targetu i nie zmienia się dla kontroli; dane potwierdzają korelację, ale nie semantykę sygnału.",
        "next_experiments": [
            "Powtórz eksperyment w przeciwnym stanie i sprawdź przejście 1->0."
        ],
        "warnings": ["Nazwa markera nie jest dowodem znaczenia sygnału."],
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
