from __future__ import annotations

import argparse
import csv
import os
import pickle
import sys
import traceback
from pathlib import Path

from app.logical_records import (
    load_recent_logical_messages,
    logical_message_path_for_session,
)
from app.session_stream import SessionPagedReader


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CRT logical-message worker for the embedded session tab"
    )
    parser.add_argument("session", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dbc", action="append", default=[], type=Path)
    return parser.parse_args()


def _status(text: str) -> None:
    print(f"STATUS\t{text}", flush=True)


def _progress(value: int) -> None:
    print(f"PROGRESS\t{max(0, min(100, int(value)))}", flush=True)


def _message_capacity_hint(session_path: Path) -> tuple[int, str]:
    message_path = logical_message_path_for_session(session_path)
    if message_path.is_file():
        _status(f"Zliczanie rekordów w {message_path.name}…")
        _progress(10)
        with message_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            if reader.fieldnames is None:
                raise ValueError("logical message CSV does not contain a header")
            total = sum(1 for _row in reader)
        return max(1, total), "messages.csv"

    _status("Brak messages.csv — przygotowanie pełnej rekonstrukcji z surowych ramek…")
    _progress(10)
    frame_count = SessionPagedReader(session_path).frame_count
    # A transport pipeline cannot emit more completed/flushed logical messages
    # than the number of source CAN frames, so the raw frame count is a safe
    # capacity for retaining the complete reconstruction.
    return max(1, frame_count), "surowa sesja"


def main() -> int:
    args = _parse_args()
    temporary_output = args.output.with_suffix(args.output.suffix + ".tmp")
    try:
        max_rows, source_hint = _message_capacity_hint(args.session)
        _status(
            f"Ładowanie wszystkich wiadomości logicznych — źródło: {source_hint}…"
        )
        _progress(25)
        messages, total, source = load_recent_logical_messages(
            args.session,
            max_rows=max_rows,
            dbc_paths=tuple(args.dbc),
        )
        _progress(80)
        _status(
            f"Przygotowanie wszystkich {len(messages):,} rekordów do wyświetlenia…".replace(
                ",", " "
            )
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with temporary_output.open("wb") as handle:
            pickle.dump(
                {
                    "path": str(args.session),
                    "messages": messages,
                    "total": int(total),
                    "source": str(source),
                },
                handle,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
            handle.flush()
            os.fsync(handle.fileno())
        _progress(95)
        os.replace(temporary_output, args.output)
        print(f"RESULT\t{args.output}", flush=True)
        _progress(100)
        return 0
    except BaseException:
        traceback.print_exc(file=sys.stderr)
        try:
            temporary_output.unlink(missing_ok=True)
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
