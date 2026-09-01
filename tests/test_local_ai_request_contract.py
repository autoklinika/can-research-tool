from __future__ import annotations

import json

import pytest

import app.local_ai as local_ai
from app.local_ai import LocalAIConfig, OpenAICompatibleLocalClient


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self, _limit: int) -> bytes:
        return self.raw


def test_openai_compatible_request_disables_reasoning_and_bounds_completion(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            {
                "model": "qwen3.6:35b-hermes64k",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "name": "unknown_bit_state_candidate",
                                    "physical_meaning": "Unknown correlated state.",
                                    "unit": None,
                                    "scale": None,
                                    "offset": None,
                                    "confidence": 0.2,
                                    "rationale": "Evidence supports correlation only.",
                                    "next_experiments": ["Repeat the inverse transition."],
                                    "warnings": ["Marker labels are not proof."],
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 500, "completion_tokens": 100},
            }
        )

    monkeypatch.setattr(local_ai, "urlopen", fake_urlopen)
    config = LocalAIConfig(
        base_url="http://192.168.1.55:11434/v1",
        model="qwen3.6:35b-hermes64k",
        timeout_s=120,
    )
    completion = OpenAICompatibleLocalClient(config).complete(
        system_prompt="system",
        user_prompt="user",
    )

    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["reasoning_effort"] == "none"
    assert request_payload["max_tokens"] == 768
    assert request_payload["temperature"] == pytest.approx(0.0)
    assert request_payload["stream"] is False
    assert request_payload["response_format"] == {"type": "json_object"}
    assert captured["timeout"] == pytest.approx(120.0)
    assert completion.request_options == {
        "reasoning_effort": "none",
        "max_tokens": 768,
    }


def test_local_ai_timeout_can_be_extended_to_300_seconds() -> None:
    config = LocalAIConfig(
        base_url="http://127.0.0.1:11434/v1",
        model="qwen",
        timeout_s=300,
    )
    assert config.timeout_s == pytest.approx(300.0)

    with pytest.raises(ValueError, match="between 1 and 300"):
        LocalAIConfig(
            base_url="http://127.0.0.1:11434/v1",
            model="qwen",
            timeout_s=301,
        )


def test_local_ai_reasoning_and_completion_limits_are_validated() -> None:
    with pytest.raises(ValueError, match="reasoning_effort"):
        LocalAIConfig(
            base_url="http://127.0.0.1:11434/v1",
            model="qwen",
            reasoning_effort="extreme",
        )

    with pytest.raises(ValueError, match="max_tokens"):
        LocalAIConfig(
            base_url="http://127.0.0.1:11434/v1",
            model="qwen",
            max_tokens=32,
        )
