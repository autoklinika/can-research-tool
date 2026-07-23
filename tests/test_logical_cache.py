from __future__ import annotations

from pathlib import Path

from app.logical_cache import (
    ensure_logical_cache,
    logical_cache_path_for_session,
    open_logical_cache_readonly,
)
from app.models import CanFrame, CaptureSession
from app.session_stream import SessionStreamWriter


def _write_session(path: Path, payload: bytes = b"\x02\x3E\x00") -> None:
    with SessionStreamWriter(CaptureSession(name="cache", source="test"), path) as writer:
        writer.append(
            CanFrame(
                sequence=0,
                timestamp_ns=1_000_000,
                arbitration_id=0x18DA00F9,
                data=payload,
                is_extended_id=True,
            )
        )


def test_logical_cache_is_reused_when_inputs_are_unchanged(tmp_path: Path) -> None:
    session = tmp_path / "sample.crt.jsonl"
    _write_session(session)
    progress: list[int] = []

    first = ensure_logical_cache(session, progress=progress.append)
    second = ensure_logical_cache(session)

    assert first.reused is False
    assert second.reused is True
    assert first.path == logical_cache_path_for_session(session)
    assert first.path.is_file()
    assert first.total_messages == 1
    assert progress[-1] == 100
    with open_logical_cache_readonly(first.path) as connection:
        row = connection.execute(
            "SELECT protocol, transport, name FROM messages"
        ).fetchone()
    assert tuple(row) == ("uds", "isotp", "UDS REQ 0x3E TesterPresent sub 0x00")


def test_logical_cache_is_invalidated_when_source_changes(tmp_path: Path) -> None:
    session = tmp_path / "sample.crt.jsonl"
    _write_session(session)
    first = ensure_logical_cache(session)

    _write_session(session, payload=b"\x02\x10\x03")
    rebuilt = ensure_logical_cache(session)

    assert first.reused is False
    assert rebuilt.reused is False
    assert rebuilt.fingerprint != first.fingerprint
    with open_logical_cache_readonly(rebuilt.path) as connection:
        name = connection.execute("SELECT name FROM messages").fetchone()[0]
    assert "DiagnosticSessionControl" in name
