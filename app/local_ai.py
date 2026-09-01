from __future__ import annotations

import ipaddress
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class LocalAIError(RuntimeError):
    """Base error for the optional local AI adapter."""


class LocalAIUnavailable(LocalAIError):
    """The configured local AI endpoint could not complete a request."""


@dataclass(frozen=True, slots=True)
class LocalAIConfig:
    base_url: str
    model: str
    timeout_s: float = 30.0
    api_key: str = ""
    max_tokens: int = 768
    reasoning_effort: str = "none"

    def __post_init__(self) -> None:
        base_url = self.base_url.strip().rstrip("/")
        model = self.model.strip()
        timeout_s = float(self.timeout_s)
        max_tokens = int(self.max_tokens)
        reasoning_effort = self.reasoning_effort.strip().lower()
        if not base_url:
            raise ValueError("local AI base URL cannot be empty")
        if not model:
            raise ValueError("local AI model cannot be empty")
        if not 1.0 <= timeout_s <= 300.0:
            raise ValueError("local AI timeout must be between 1 and 300 seconds")
        if not 64 <= max_tokens <= 4096:
            raise ValueError("local AI max_tokens must be between 64 and 4096")
        if reasoning_effort not in {"none", "low", "medium", "high"}:
            raise ValueError("local AI reasoning_effort must be none, low, medium or high")
        _validate_local_url(base_url)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "timeout_s", timeout_s)
        object.__setattr__(self, "api_key", self.api_key.strip())
        object.__setattr__(self, "max_tokens", max_tokens)
        object.__setattr__(self, "reasoning_effort", reasoning_effort)

    @classmethod
    def from_environment(cls) -> "LocalAIConfig":
        return cls(
            base_url=os.environ.get("CRT_AI_BASE_URL", "http://127.0.0.1:11434/v1"),
            model=os.environ.get("CRT_AI_MODEL", "qwen3.6:35b-hermes64k"),
            timeout_s=float(os.environ.get("CRT_AI_TIMEOUT_S", "30")),
            api_key=os.environ.get("CRT_AI_API_KEY", ""),
            max_tokens=int(os.environ.get("CRT_AI_MAX_TOKENS", "768")),
            reasoning_effort=os.environ.get("CRT_AI_REASONING_EFFORT", "none"),
        )


@dataclass(frozen=True, slots=True)
class LocalAICompletion:
    provider: str
    model: str
    endpoint: str
    content: str
    latency_ms: float
    usage: Mapping[str, Any]
    request_options: Mapping[str, Any] = field(default_factory=dict)


class LocalAIClient(Protocol):
    @property
    def config(self) -> LocalAIConfig:
        ...

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        cancellation: object | None = None,
    ) -> LocalAICompletion:
        ...


class OpenAICompatibleLocalClient:
    """Small dependency-free client for Ollama/OpenAI-compatible local endpoints.

    The client deliberately accepts only localhost/private-LAN destinations by
    default. CRT never sends RAW sessions through this adapter; callers decide
    the bounded structured context that is supplied to the model.

    Signal Hypothesis requests default to reasoning_effort=none because CRT
    needs a short auditable structured suggestion rather than hidden extended
    reasoning. max_tokens bounds completion time and response size.
    """

    provider_name = "openai-compatible-local"

    def __init__(self, config: LocalAIConfig) -> None:
        self._config = config

    @property
    def config(self) -> LocalAIConfig:
        return self._config

    @property
    def endpoint(self) -> str:
        base = self._config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        cancellation: object | None = None,
    ) -> LocalAICompletion:
        _raise_if_cancelled(cancellation)
        request_options = {
            "reasoning_effort": self._config.reasoning_effort,
            "max_tokens": self._config.max_tokens,
        }
        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": str(system_prompt)},
                {"role": "user", "content": str(user_prompt)},
            ],
            "temperature": 0.0,
            "stream": False,
            "response_format": {"type": "json_object"},
            **request_options,
        }
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=self._config.timeout_s) as response:
                raw = response.read(4 * 1024 * 1024)
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(1024).decode("utf-8", errors="replace").strip()
            except Exception:
                detail = ""
            suffix = f": {detail}" if detail else ""
            raise LocalAIUnavailable(f"local AI HTTP {exc.code}{suffix}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise LocalAIUnavailable(f"local AI unavailable: {exc}") from exc
        latency_ms = (time.perf_counter() - started) * 1000.0
        _raise_if_cancelled(cancellation)
        try:
            decoded = json.loads(raw.decode("utf-8"))
            choices = decoded.get("choices")
            message = choices[0].get("message") if isinstance(choices, list) and choices else None
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise ValueError("response has no assistant content")
            usage = decoded.get("usage")
            usage = dict(usage) if isinstance(usage, dict) else {}
            model = str(decoded.get("model") or self._config.model)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, IndexError) as exc:
            raise LocalAIUnavailable(f"invalid local AI response: {exc}") from exc
        return LocalAICompletion(
            provider=self.provider_name,
            model=model,
            endpoint=self.endpoint,
            content=content.strip(),
            latency_ms=round(latency_ms, 3),
            usage=usage,
            request_options=request_options,
        )


def extract_json_object(content: str) -> dict[str, Any]:
    """Extract one JSON object from a model response without accepting prose as data."""

    text = str(content).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise LocalAIError("AI response does not contain a JSON object")
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LocalAIError(f"AI response JSON is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise LocalAIError("AI response JSON must be an object")
    return value


def _raise_if_cancelled(cancellation: object | None) -> None:
    if cancellation is None:
        return
    callback = getattr(cancellation, "raise_if_cancelled", None)
    if callable(callback):
        callback()


def _validate_local_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("local AI URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("credentials must not be embedded in local AI URL")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("local AI URL has no hostname")
    if host == "localhost" or host.endswith(".local") or host.endswith(".lan"):
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Single-label hostnames are commonly resolved only inside a LAN.
        if "." not in host:
            return
        raise ValueError("Signal Hypothesis Stage 1 rejects public AI endpoints")
    if address.is_private or address.is_loopback or address.is_link_local:
        return
    raise ValueError("Signal Hypothesis Stage 1 rejects public AI endpoints")


__all__ = [
    "LocalAIClient",
    "LocalAICompletion",
    "LocalAIConfig",
    "LocalAIError",
    "LocalAIUnavailable",
    "OpenAICompatibleLocalClient",
    "extract_json_object",
]
