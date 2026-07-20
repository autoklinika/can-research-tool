from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import CanFrame, CaptureSession


_FORMAT = "crt-session-jsonl"
_VERSION = 1
_INDEX_FORMAT = "crt-session-index"
_INDEX_VERSION = 1


@dataclass(frozen=True, slots=True)
class SessionIndex:
    frame_count: int
    stride: int
    checkpoints: tuple[tuple[int, int], ...]
    file_size: int


class SessionStreamWriter:
    """Append CAN frames directly to a crash-readable JSONL session.

    Only a bounded amount of state is retained in memory. A sparse byte-offset
    sidecar is written on clean close so completed sessions can be opened in
    pages without loading every frame into RAM.
    """

    def __init__(
        self,
        session: CaptureSession,
        path: str | Path,
        *,
        flush_every: int = 256,
        index_stride: int = 4096,
    ) -> None:
        if flush_every <= 0:
            raise ValueError("flush_every must be greater than zero")
        if index_stride <= 0:
            raise ValueError("index_stride must be greater than zero")

        self.session = session
        self.path = Path(path)
        self.index_path = _index_path(self.path)
        self.flush_every = flush_every
        self.index_stride = index_stride
        self._handle = None
        self._frame_count = 0
        self._last_sequence: int | None = None
        self._checkpoints: list[tuple[int, int]] = []
        self._closed = False

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def is_open(self) -> bool:
        return self._handle is not None and not self._closed

    def open(self) -> None:
        if self.is_open:
            return
        if self._closed:
            raise RuntimeError("session stream writer cannot be reopened")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("wb")
        self._write_record(_session_header(self.session))
        self._handle.flush()

    def append(self, frame: CanFrame) -> None:
        if not self.is_open:
            raise RuntimeError("session stream writer is not open")
        if self._last_sequence is not None and frame.sequence <= self._last_sequence:
            raise ValueError("frame sequence must be strictly increasing")

        assert self._handle is not None
        if self._frame_count % self.index_stride == 0:
            self._checkpoints.append((self._frame_count, self._handle.tell()))

        self._write_record(_frame_record(frame))
        self._frame_count += 1
        self._last_sequence = frame.sequence

        if self._frame_count % self.flush_every == 0:
            self._handle.flush()

    def close(self, metadata: dict[str, Any] | None = None) -> None:
        if self._closed:
            return
        self._closed = True

        handle = self._handle
        self._handle = None
        if handle is None:
            return

        footer = {
            "record": "session_end",
            "frame_count": self._frame_count,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "metadata": dict(metadata or {}),
        }
        handle.write(_encode_record(footer))
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()

        index = SessionIndex(
            frame_count=self._frame_count,
            stride=self.index_stride,
            checkpoints=tuple(self._checkpoints),
            file_size=self.path.stat().st_size,
        )
        _write_index(self.index_path, index)

    def _write_record(self, record: dict[str, Any]) -> None:
        assert self._handle is not None
        self._handle.write(_encode_record(record))

    def __enter__(self) -> "SessionStreamWriter":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close({"clean_close": exc_type is None})


class SessionPagedReader:
    """Read selected frame ranges from a CRT session using sparse offsets."""

    def __init__(self, path: str | Path, *, index_stride: int = 4096) -> None:
        if index_stride <= 0:
            raise ValueError("index_stride must be greater than zero")
        self.path = Path(path)
        self.index_path = _index_path(self.path)
        self.session = read_session_header(self.path)
        self.index = self._load_or_build_index(index_stride)

    @property
    def frame_count(self) -> int:
        return self.index.frame_count

    def read_page(self, start: int, limit: int) -> list[CanFrame]:
        if start < 0:
            raise ValueError("start cannot be negative")
        if limit < 0:
            raise ValueError("limit cannot be negative")
        if limit == 0 or start >= self.frame_count:
            return []
        return list(self.iter_frames(start=start, limit=limit))

    def iter_frames(
        self,
        *,
        start: int = 0,
        limit: int | None = None,
    ) -> Iterator[CanFrame]:
        if start < 0:
            raise ValueError("start cannot be negative")
        if limit is not None and limit < 0:
            raise ValueError("limit cannot be negative")
        if start >= self.frame_count or limit == 0:
            return

        checkpoint_frame, checkpoint_offset = self._checkpoint_for(start)
        current_index = checkpoint_frame
        emitted = 0

        with self.path.open("rb") as handle:
            handle.seek(checkpoint_offset)
            for raw_line in handle:
                if not raw_line.strip():
                    continue
                record = json.loads(raw_line)
                record_type = record.get("record")
                if record_type == "session_end":
                    break
                if record_type != "frame":
                    continue
                if current_index < start:
                    current_index += 1
                    continue
                yield _frame_from_record(record)
                current_index += 1
                emitted += 1
                if limit is not None and emitted >= limit:
                    break

    def _checkpoint_for(self, start: int) -> tuple[int, int]:
        selected = self.index.checkpoints[0] if self.index.checkpoints else (0, 0)
        for checkpoint in self.index.checkpoints:
            if checkpoint[0] > start:
                break
            selected = checkpoint
        return selected

    def _load_or_build_index(self, stride: int) -> SessionIndex:
        current_size = self.path.stat().st_size
        try:
            index = _read_index(self.index_path)
            if index.file_size == current_size:
                return index
        except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError):
            pass

        index = _build_index(self.path, stride)
        _write_index(self.index_path, index)
        return index


def read_session_header(path: str | Path) -> CaptureSession:
    source = Path(path)
    with source.open("rb") as handle:
        first_line = handle.readline()
    if not first_line:
        raise ValueError("empty CRT session file")

    header: dict[str, Any] = json.loads(first_line)
    if header.get("record") != "session" or header.get("format") != _FORMAT:
        raise ValueError("unsupported CRT session header")
    if header.get("version") != _VERSION:
        raise ValueError(f"unsupported CRT session version: {header.get('version')}")

    return CaptureSession(
        name=str(header.get("name", source.stem)),
        source=str(header.get("source", "unknown")),
        started_at_utc=str(header.get("started_at_utc", "")),
        bitrate=header.get("bitrate"),
        channel=header.get("channel"),
        adapter=str(header.get("adapter", "")),
        notes=str(header.get("notes", "")),
        metadata=dict(header.get("metadata") or {}),
    )


def iter_session_frames(path: str | Path) -> Iterator[CanFrame]:
    """Sequentially iterate frames without constructing ``CaptureSession.frames``."""

    source = Path(path)
    with source.open("rb") as handle:
        first_line = handle.readline()
        if not first_line:
            raise ValueError("empty CRT session file")
        header = json.loads(first_line)
        if header.get("record") != "session" or header.get("format") != _FORMAT:
            raise ValueError("unsupported CRT session header")
        if header.get("version") != _VERSION:
            raise ValueError(f"unsupported CRT session version: {header.get('version')}")

        for line_number, raw_line in enumerate(handle, start=2):
            if not raw_line.strip():
                continue
            record = json.loads(raw_line)
            record_type = record.get("record")
            if record_type == "session_end":
                break
            if record_type != "frame":
                raise ValueError(f"unexpected record at line {line_number}")
            yield _frame_from_record(record)


def _session_header(session: CaptureSession) -> dict[str, Any]:
    return {
        "record": "session",
        "format": _FORMAT,
        "version": _VERSION,
        "name": session.name,
        "source": session.source,
        "started_at_utc": session.started_at_utc,
        "bitrate": session.bitrate,
        "channel": session.channel,
        "adapter": session.adapter,
        "notes": session.notes,
        "metadata": session.metadata,
    }


def _frame_record(frame: CanFrame) -> dict[str, Any]:
    return {
        "record": "frame",
        "sequence": frame.sequence,
        "timestamp_ns": frame.timestamp_ns,
        "arbitration_id": frame.arbitration_id,
        "data": frame.data.hex().upper(),
        "channel": frame.channel,
        "is_extended_id": frame.is_extended_id,
        "is_remote_frame": frame.is_remote_frame,
        "is_error_frame": frame.is_error_frame,
        "source_timestamp": frame.source_timestamp,
        "source_flags": frame.source_flags,
    }


def _frame_from_record(record: dict[str, Any]) -> CanFrame:
    return CanFrame(
        sequence=int(record["sequence"]),
        timestamp_ns=int(record["timestamp_ns"]),
        arbitration_id=int(record["arbitration_id"]),
        data=bytes.fromhex(str(record.get("data", ""))),
        channel=int(record.get("channel", 0)),
        is_extended_id=bool(record.get("is_extended_id", False)),
        is_remote_frame=bool(record.get("is_remote_frame", False)),
        is_error_frame=bool(record.get("is_error_frame", False)),
        source_timestamp=(
            int(record["source_timestamp"])
            if record.get("source_timestamp") is not None
            else None
        ),
        source_flags=int(record.get("source_flags", 0)),
    )


def _build_index(path: Path, stride: int) -> SessionIndex:
    checkpoints: list[tuple[int, int]] = []
    frame_count = 0

    with path.open("rb") as handle:
        first_line = handle.readline()
        if not first_line:
            raise ValueError("empty CRT session file")
        header = json.loads(first_line)
        if header.get("record") != "session" or header.get("format") != _FORMAT:
            raise ValueError("unsupported CRT session header")

        while True:
            offset = handle.tell()
            raw_line = handle.readline()
            if not raw_line:
                break
            if not raw_line.strip():
                continue
            record = json.loads(raw_line)
            record_type = record.get("record")
            if record_type == "session_end":
                break
            if record_type != "frame":
                continue
            if frame_count % stride == 0:
                checkpoints.append((frame_count, offset))
            frame_count += 1

    return SessionIndex(
        frame_count=frame_count,
        stride=stride,
        checkpoints=tuple(checkpoints),
        file_size=path.stat().st_size,
    )


def _write_index(path: Path, index: SessionIndex) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": _INDEX_FORMAT,
        "version": _INDEX_VERSION,
        "frame_count": index.frame_count,
        "stride": index.stride,
        "checkpoints": [list(item) for item in index.checkpoints],
        "file_size": index.file_size,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_index(path: Path) -> SessionIndex:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != _INDEX_FORMAT or payload.get("version") != _INDEX_VERSION:
        raise ValueError("unsupported CRT session index")
    return SessionIndex(
        frame_count=int(payload["frame_count"]),
        stride=int(payload["stride"]),
        checkpoints=tuple(
            (int(frame_number), int(byte_offset))
            for frame_number, byte_offset in payload.get("checkpoints", [])
        ),
        file_size=int(payload["file_size"]),
    )


def _index_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".idx.json")


def _encode_record(record: dict[str, Any]) -> bytes:
    return (
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
