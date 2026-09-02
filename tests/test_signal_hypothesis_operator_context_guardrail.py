from __future__ import annotations

import json

import pytest

from app.local_ai import extract_json_object
from app.signal_hypothesis_guardrail import apply_operator_context_guardrail


def _prompt(*, operator_context: str | None) -> dict[str, object]:
    return {
        "operator_context": operator_context,
        "candidate": {
            "candidate_score": 1.0,
            "strength": "strong",
            "arbitration_id": 0x321,
            "arbitration_id_hex": "0x321",
            "byte_index": 0,
            "bit_index": 2,
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
                "timing": {"mean_delay_ns": 70_000_000},
            },
        },
    }


def _overclaiming_model_response() -> str:
    return json.dumps(
        {
            "name": "EGR_valve_open_command",
            "physical_meaning": (
                "Bit bezpośrednio steruje zaworem EGR; 0 oznacza zamknięcie, "
                "a 1 oznacza otwarcie zaworu."
            ),
            "unit": "%",
            "scale": 1.0,
            "offset": 0.0,
            "confidence": 0.9,
            "rationale": (
                "Przejście 0->1 po odłączeniu dowodzi, że jest to komenda otwarcia EGR."
            ),
            "next_experiments": [
                "Sprawdź, czy bit 4 wraca do stanu 0 po podłączeniu EGR.",
                "Odetnij dopływ powietrza i obserwuj ciśnienie w kolektorze.",
            ],
            "warnings": ["Model uważa interpretację za bardzo prawdopodobną."],
        },
        ensure_ascii=False,
    )


def test_operator_context_is_domain_hint_not_bit_semantics() -> None:
    context = (
        "Test dotyczy układu EGR. Marker oznacza moment fizycznego odłączenia EGR. "
        "Traktuj tę informację tylko jako kontekst eksperymentu."
    )
    result = apply_operator_context_guardrail(
        _overclaiming_model_response(),
        _prompt(operator_context=context),
    )
    hypothesis = extract_json_object(result)

    assert hypothesis["name"] == "operator_context_correlated_candidate"
    assert "Test dotyczy układu EGR." in hypothesis["physical_meaning"]
    assert "funkcji bitu" in hypothesis["physical_meaning"]
    assert "stanów 0 i 1" in hypothesis["physical_meaning"]
    assert hypothesis["unit"] is None
    assert hypothesis["scale"] is None
    assert hypothesis["offset"] is None
    assert hypothesis["confidence"] == pytest.approx(0.35)

    persisted_semantics = " ".join(
        [
            hypothesis["name"],
            hypothesis["physical_meaning"],
            hypothesis["rationale"],
            *hypothesis["warnings"],
        ]
    ).lower()
    assert "otwarcie zaworu" not in persisted_semantics
    assert "zamknięcie" not in persisted_semantics
    assert "komenda otwarcia" not in persisted_semantics
    assert "bezpośrednio steruje" not in persisted_semantics

    assert "score kandydata wynosi 1.000" in hypothesis["rationale"]
    assert "6/6" in hypothesis["rationale"]
    assert "0/4" in hypothesis["rationale"]
    assert "0->1" in hypothesis["rationale"]
    assert "70.0 ms" in hypothesis["rationale"]
    assert "nie identyfikują funkcji bitu" in hypothesis["rationale"]

    experiments = hypothesis["next_experiments"]
    assert len(experiments) == 3
    assert all("0x321 B0.2" in item for item in experiments)
    assert "0->1" in experiments[0]
    assert "70.0 ms" in experiments[0]
    assert "1→0" in experiments[1]
    experiment_text = " ".join(experiments).lower()
    assert "bit 4" not in experiment_text
    assert "kolektor" not in experiment_text
    assert "dopływ powietrza" not in experiment_text

    assert hypothesis["warnings"] == [
        "Kontekst operatora jest wskazówką semantyczną, a nie dowodem znaczenia sygnału.",
        "CRT nie przypisuje znaczenia stanom 0/1 ani roli komenda/pomiar bez osobnego evidence.",
        "Silna korelacja z eksperymentem nie potwierdza funkcji fizycznej kandydata.",
    ]


def test_operator_context_guardrail_does_nothing_without_context() -> None:
    original = _overclaiming_model_response()
    assert apply_operator_context_guardrail(original, _prompt(operator_context=None)) == original
