from __future__ import annotations

import argparse
import os
import pickle
import sys
import traceback
from pathlib import Path

from app.logical_records import load_recent_logical_messages


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CRT logical-message worker for the embedded session tab"
    )
    parser.add_argument("session", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-rows", type=int, default=1_000)
    parser.add_argument("--dbc", action="append", default=[], type=Path)
    return parser.parse_args()


def _status(text: str) -> None:
    print(f"STATUS\t{text}", flush=True)


def main() -> int:
    args = _parse_args()
    temporary_output = args.output.with_suffix(args.output.suffix + ".tmp")
    try:
        _status(f"Odczyt pliku wiadomości dla {args.session.name}…")
        messages, total, source = load_recent_logical_messages(
            args.session,
            max_rows=args.max_rows,
            dbc_paths=tuple(args.dbc),
        )
        _status(
            f"Przygotowanie {len(messages):,} rekordów do wyświetlenia…".replace(
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
        os.replace(temporary_output, args.output)
        print(f"RESULT\t{args.output}", flush=True)
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
