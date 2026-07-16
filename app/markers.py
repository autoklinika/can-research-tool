from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class MarkerPreset:
    """User-defined marker available before and during a capture."""

    id: str
    name: str
    shortcut: str
    color: str = "#3B82F6"
    area: str = ""
    enabled: bool = True
    sort_order: int = 0

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("marker preset id cannot be empty")
        if not self.name.strip():
            raise ValueError("marker preset name cannot be empty")
        if not self.shortcut.strip():
            raise ValueError("marker preset shortcut cannot be empty")

    @classmethod
    def create(
        cls,
        name: str,
        shortcut: str,
        *,
        color: str = "#3B82F6",
        area: str = "",
        enabled: bool = True,
        sort_order: int = 0,
    ) -> "MarkerPreset":
        return cls(
            id=str(uuid4()),
            name=name.strip(),
            shortcut=shortcut.strip(),
            color=color.strip() or "#3B82F6",
            area=area.strip(),
            enabled=enabled,
            sort_order=sort_order,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MarkerPreset":
        return cls(
            id=str(payload["id"]),
            name=str(payload["name"]),
            shortcut=str(payload["shortcut"]),
            color=str(payload.get("color", "#3B82F6")),
            area=str(payload.get("area", "")),
            enabled=bool(payload.get("enabled", True)),
            sort_order=int(payload.get("sort_order", 0)),
        )


@dataclass(frozen=True, slots=True)
class CaptureMarker:
    """Immutable marker snapshot stored in a session at event time."""

    id: str
    timestamp_ns: int
    preset_id: str
    name: str
    shortcut: str
    color: str
    area: str
    source: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.timestamp_ns < 0:
            raise ValueError("marker timestamp cannot be negative")
        if not self.id.strip():
            raise ValueError("marker id cannot be empty")
        if not self.name.strip():
            raise ValueError("marker name cannot be empty")

    @classmethod
    def from_preset(
        cls,
        preset: MarkerPreset,
        timestamp_ns: int,
        *,
        source: str,
        note: str = "",
    ) -> "CaptureMarker":
        return cls(
            id=str(uuid4()),
            timestamp_ns=timestamp_ns,
            preset_id=preset.id,
            name=preset.name,
            shortcut=preset.shortcut,
            color=preset.color,
            area=preset.area,
            source=source,
            note=note,
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "record": "marker",
            "id": self.id,
            "timestamp_ns": self.timestamp_ns,
            "preset_id": self.preset_id,
            "name": self.name,
            "shortcut": self.shortcut,
            "color": self.color,
            "area": self.area,
            "source": self.source,
            "note": self.note,
        }

    @classmethod
    def from_record(cls, payload: dict[str, Any]) -> "CaptureMarker":
        return cls(
            id=str(payload["id"]),
            timestamp_ns=int(payload["timestamp_ns"]),
            preset_id=str(payload.get("preset_id", "")),
            name=str(payload["name"]),
            shortcut=str(payload.get("shortcut", "")),
            color=str(payload.get("color", "#3B82F6")),
            area=str(payload.get("area", "")),
            source=str(payload.get("source", "unknown")),
            note=str(payload.get("note", "")),
        )
