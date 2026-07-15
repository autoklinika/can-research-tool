from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import CanFrame, CaptureSession


_FORMAT = "crt-session-jsonl"
_VERSION = 1


def save_session(session: CaptureSession, path: str | Path) -> None:
    """Save a session as streaming-friendly JSON Lines."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    header = {
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

    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(header, ensure_ascii=False, separators=(",", ":")) + "\n")
        for frame in session.frames:
            record = {
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
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def load_session(path: str | Path) -> CaptureSession:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        first_line = handle.readline()
        if not first_line:
            raise ValueError("empty CRT session file")
        header: dict[str, Any] = json.loads(first_line)
        if header.get("record") != "session" or header.get("format") != _FORMAT:
            raise ValueError("unsupported CRT session header")
        if header.get("version") != _VERSION:
            raise ValueError(f"unsupported CRT session version: {header.get('version')}")

        session = CaptureSession(
            name=str(header.get("name", source.stem)),
            source=str(header.get("source", "unknown")),
            started_at_utc=str(header.get("started_at_utc", "")),
            bitrate=header.get("bitrate"),
            channel=header.get("channel"),
            adapter=str(header.get("adapter", "")),
            notes=str(header.get("notes", "")),
            metadata=dict(header.get("metadata") or {}),
        )

        for line_number, line in enumerate(handle, start=2):
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("record") != "frame":
                raise ValueError(f"unexpected record at line {line_number}")
            session.append(
                CanFrame(
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
            )

    return session
