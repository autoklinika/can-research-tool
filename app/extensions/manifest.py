from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


CRT_EXTENSION_API_VERSION = "1"

_EXTENSION_ID_RE = re.compile(r"^crt\.[a-z0-9][a-z0-9_.-]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_API_RE = re.compile(r"^\d+$")


class ExtensionType(StrEnum):
    FILTER = "filter"
    ANALYSIS = "analysis"
    PATTERN = "pattern"
    DECODER = "decoder"
    COMPARISON = "comparison"
    ARTIFACT = "artifact"
    EXPORT = "export"
    AI = "ai"
    ACTIVE_SCENARIO = "active_scenario"


class ExtensionPermission(StrEnum):
    PROJECT_READ = "project.read"
    SESSION_READ = "session.read"
    ARTIFACT_READ = "artifact.read"
    ARTIFACT_WRITE = "artifact.write"
    FINDING_WRITE = "finding.write"
    AI_USE = "ai.use"
    CAN_TX = "can.tx"


@dataclass(frozen=True, slots=True)
class ExtensionManifest:
    id: str
    name: str
    version: str
    crt_api: str
    type: ExtensionType
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    live_supported: bool = False
    requires_ai: bool = False
    requires_can_tx: bool = False
    permissions: tuple[ExtensionPermission, ...] = ()

    def __post_init__(self) -> None:
        if not _EXTENSION_ID_RE.fullmatch(self.id):
            raise ValueError(f"invalid extension id: {self.id!r}")
        if not self.name.strip():
            raise ValueError("extension name cannot be empty")
        if not _SEMVER_RE.fullmatch(self.version):
            raise ValueError(f"invalid extension version: {self.version!r}")
        if not _API_RE.fullmatch(self.crt_api):
            raise ValueError(f"invalid CRT extension API version: {self.crt_api!r}")
        _validate_tokens(self.inputs, "inputs")
        _validate_tokens(self.outputs, "outputs")
        if len(set(self.permissions)) != len(self.permissions):
            raise ValueError("extension permissions must be unique")
        has_can_tx = ExtensionPermission.CAN_TX in self.permissions
        if self.requires_can_tx != has_can_tx:
            raise ValueError(
                "requires_can_tx and can.tx permission must be declared together"
            )
        has_ai = ExtensionPermission.AI_USE in self.permissions
        if self.requires_ai != has_ai:
            raise ValueError("requires_ai and ai.use permission must be declared together")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExtensionManifest":
        required = {"id", "name", "version", "crt_api", "type"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"extension manifest is missing fields: {missing}")
        return cls(
            id=str(payload["id"]),
            name=str(payload["name"]),
            version=str(payload["version"]),
            crt_api=str(payload["crt_api"]),
            type=ExtensionType(str(payload["type"])),
            inputs=_string_tuple(payload.get("inputs", ()), "inputs"),
            outputs=_string_tuple(payload.get("outputs", ()), "outputs"),
            live_supported=_strict_bool(payload.get("live_supported", False), "live_supported"),
            requires_ai=_strict_bool(payload.get("requires_ai", False), "requires_ai"),
            requires_can_tx=_strict_bool(
                payload.get("requires_can_tx", False), "requires_can_tx"
            ),
            permissions=tuple(
                ExtensionPermission(item)
                for item in _string_tuple(payload.get("permissions", ()), "permissions")
            ),
        )

    @classmethod
    def from_json(cls, content: str) -> "ExtensionManifest":
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("extension manifest JSON must contain an object")
        return cls.from_mapping(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "crt_api": self.crt_api,
            "type": self.type.value,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "live_supported": self.live_supported,
            "requires_ai": self.requires_ai,
            "requires_can_tx": self.requires_can_tx,
            "permissions": [permission.value for permission in self.permissions],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _validate_tokens(values: tuple[str, ...], name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"extension manifest {name} must be unique")
    for value in values:
        if not value or value != value.strip():
            raise ValueError(f"extension manifest {name} contains an invalid token")


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"extension manifest {name} must be a list")
    result = tuple(str(item) for item in value)
    _validate_tokens(result, name)
    return result


def _strict_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"extension manifest {name} must be boolean")
    return value
