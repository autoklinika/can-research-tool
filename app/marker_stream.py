from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

from .markers import CaptureMarker, MarkerPreset


_FORMAT = "crt-session-markers-jsonl"
_VERSION = 1


class MarkerStreamWriter:
    """Append timestamped operator markers without blocking capture."""

    def __init__(
        self,
        path: str | Path,
        *,
        presets: tuple[MarkerPreset, ...] = (),
        flush_every: int = 1,
    ) -> None:
        if flush_every <= 0:
            raise ValueError("flush_every must be greater than zero")
        self.path = Path(path)
        self.presets = presets
        self.flush_every = flush_every
        self._handle = None
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def open(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("wb")
        header = {
            "record": "marker_session",
            "format": _FORMAT,
            "version": _VERSION,
            "presets": [preset.to_dict() for preset in self.presets],
        }
        self._write(header)
        self._handle.flush()

    def append(self, marker: CaptureMarker) -> None:
        if self._handle is None:
            raise RuntimeError("marker stream writer is not open")
        self._write(marker.to_record())
        self._count += 1
        if self._count % self.flush_every == 0:
            self._handle.flush()

    def close(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        self._write_to(handle, {"record": "marker_session_end", "marker_count": self._count})
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()

    def _write(self, record: dict[str, object]) -> None:
        assert self._handle is not None
        self._write_to(self._handle, record)

    @staticmethod
    def _write_to(handle, record: dict[str, object]) -> None:
        handle.write(
            (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
        )

    def __enter__(self) -> "MarkerStreamWriter":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def iter_markers(path: str | Path) -> Iterator[CaptureMarker]:
    source = Path(path)
    if not source.is_file():
        return
    with source.open("rb") as handle:
        first = handle.readline()
        if not first:
            return
        header = json.loads(first)
        if header.get("format") != _FORMAT or int(header.get("version", 0)) != _VERSION:
            raise ValueError("unsupported CRT marker stream")
        for raw_line in handle:
            if not raw_line.strip():
                continue
            record = json.loads(raw_line)
            if record.get("record") == "marker_session_end":
                break
            if record.get("record") != "marker":
                continue
            yield CaptureMarker.from_record(record)


def marker_path_for_session(session_path: str | Path) -> Path:
    path = Path(session_path)
    name = path.name
    if name.lower().endswith(".crt.jsonl"):
        name = name[: -len(".crt.jsonl")]
    else:
        name = path.stem
    return path.with_name(f"{name}.markers.jsonl")
