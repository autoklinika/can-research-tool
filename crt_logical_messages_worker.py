from __future__ import annotations

import argparse
import os
import pickle
import sys
import traceback
from pathlib import Path

from app.logical_cache import ensure_logical_cache


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CRT logical-message SQLite cache worker"
    )
    parser.add_argument("session", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dbc", action="append", default=[], type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _status(text: str) -> None:
    print(f"STATUS\t{text}", flush=True)


def _progress(value: int) -> None:
    print(f"PROGRESS\t{max(0, min(100, int(value)))}", flush=True)


def main() -> int:
    args = _parse_args()
    temporary_output = args.output.with_suffix(args.output.suffix + ".tmp")
    try:
        _status("Sprawdzanie zapisanego obrazu analitycznego…")
        _progress(2)
        info = ensure_logical_cache(
            args.session,
            dbc_paths=tuple(args.dbc),
            force=bool(args.force),
            progress=_progress,
            status=_status,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with temporary_output.open("wb") as handle:
            pickle.dump(
                {
                    "path": str(args.session),
                    "cache_path": str(info.path),
                    "total": int(info.total_messages),
                    "source": str(info.source),
                    "reused": bool(info.reused),
                    "decoder_signature": str(info.decoder_signature),
                    "dbc_signature": str(info.dbc_signature),
                },
                handle,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
            handle.flush()
            os.fsync(handle.fileno())
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
