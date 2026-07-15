from __future__ import annotations

from pathlib import Path

from .models import CaptureSession
from .session_stream import (
    SessionStreamWriter,
    iter_session_frames,
    read_session_header,
)


def save_session(session: CaptureSession, path: str | Path) -> None:
    """Save a complete in-memory session through the streaming writer.

    Existing callers retain the same API, while live capture can use
    ``SessionStreamWriter`` directly and avoid building ``session.frames``.
    """

    with SessionStreamWriter(session, path) as writer:
        for frame in session.frames:
            writer.append(frame)


def load_session(path: str | Path) -> CaptureSession:
    """Load a complete session into memory.

    This compatibility function is intended for tests and small captures.
    Large-session views should use ``SessionPagedReader`` or
    ``iter_session_frames`` instead.
    """

    session = read_session_header(path)
    for frame in iter_session_frames(path):
        session.append(frame)
    return session
