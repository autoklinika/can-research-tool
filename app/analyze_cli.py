from __future__ import annotations

import argparse
from pathlib import Path

from app.exports import save_message_summary_csv, save_messages_csv
from app.message_analysis import LogicalMessageAnalyzer, LogicalMessageStatistics
from app.protocols import ProtocolRegistry
from app.session_io import load_session
from app.transport import TransportPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze an existing CRT session without recapturing CAN traffic",
    )
    parser.add_argument("session", type=Path, help="path to a .crt.jsonl session")
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=None,
        help="output prefix; defaults to the session path without .crt.jsonl",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.session.is_file():
        raise SystemExit(f"Session file was not found: {args.session}")

    session = load_session(args.session)
    messages = TransportPipeline().process(session.frames)
    decoded = ProtocolRegistry().decode_all(messages)
    statistics = LogicalMessageAnalyzer().summarize(decoded)

    output_prefix = args.output_prefix or _default_prefix(args.session)
    messages_path = Path(f"{output_prefix}.messages.csv")
    summary_path = Path(f"{output_prefix}.messages.summary.csv")

    save_messages_csv(decoded, messages_path)
    save_message_summary_csv(statistics, summary_path)

    print("CRT — analiza zapisanej sesji")
    print(f"Sesja: {args.session}")
    print(f"Ramki: {len(session.frames)}")
    print(f"Wiadomości logiczne: {len(decoded)}")
    print(
        "Wiadomości niekompletne: "
        f"{sum(not item.message.complete for item in decoded)}"
    )
    print(f"Wiadomości: {messages_path}")
    print(f"Podsumowanie wiadomości: {summary_path}")
    _print_summary(statistics)
    return 0


def _default_prefix(session_path: Path) -> Path:
    suffix = ".crt.jsonl"
    text = str(session_path)
    return Path(text[: -len(suffix)] if text.endswith(suffix) else text)


def _print_summary(statistics: list[LogicalMessageStatistics]) -> None:
    if not statistics:
        print("\nBrak wiadomości logicznych.")
        return

    print()
    print(
        "Protokół  Transport        Identyfikator       Wiad.  Kompl.  "
        "Okres śr. [ms]  Nazwa"
    )
    print(
        "---------  ---------------  ------------------  -----  ------  "
        "--------------  ------------------------------"
    )
    for item in statistics:
        identifier = _logical_identifier(item)
        period = "-" if item.mean_period_ms is None else f"{item.mean_period_ms:.3f}"
        print(
            f"{item.protocol.value:<9}  {item.transport.value:<15}  "
            f"{identifier:<18}  {item.message_count:>5}  "
            f"{item.complete_count:>6}  {period:>14}  {item.name}"
        )


def _logical_identifier(item: LogicalMessageStatistics) -> str:
    if item.pgn is not None and item.transport.value.startswith("j1939"):
        return f"PGN 0x{item.pgn:05X}"
    if item.arbitration_id is not None:
        width = 8 if item.is_extended_id else 3
        return f"CAN 0x{item.arbitration_id:0{width}X}"
    return "-"


if __name__ == "__main__":
    raise SystemExit(main())
