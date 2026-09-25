"""Local export to stdout; shell redirection chooses the destination."""

import argparse
import sys

from .platform_export import PlatformExporter, canonical_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a CRT session; no network access")
    parser.add_argument("project")
    parser.add_argument("session_id")
    parser.add_argument("--artifact", action="append", default=[], help="Explicit artifact ID")
    parser.add_argument("--question", help="Build an AI context package instead of a manifest")
    parser.add_argument("--maximum-bytes", type=int, default=1024 * 1024)
    args = parser.parse_args(argv)
    try:
        exporter = PlatformExporter(args.project)
        selection = tuple(args.artifact)
        if args.question is not None:
            result = exporter.context(
                args.session_id,
                question=args.question,
                artifact_ids=selection,
                maximum_bytes=args.maximum_bytes,
            )
        else:
            result = exporter.manifest(args.session_id, artifact_ids=selection)
        sys.stdout.write(canonical_bytes(result).decode("utf-8") + "\n")
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        parser.exit(2, f"export failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
