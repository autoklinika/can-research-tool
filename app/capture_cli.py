from __future__ import annotations

import argparse
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from time import monotonic, perf_counter_ns

from app.analysis import CanIdStatistics, SessionAnalyzer
from app.exports import (
    save_frames_csv,
    save_message_summary_csv,
    save_messages_csv,
    save_summary_csv,
)
from app.message_analysis import LogicalMessageAnalyzer, LogicalMessageStatistics
from app.models import CaptureSession
from app.protocols import ProtocolRegistry
from app.session_io import save_session
from app.transport import TransportPipeline
from kvaser.backend import (
    KvaserPassiveChannel,
    KvaserReceiveMode,
    list_channels,
)


_BITRATES = (
    10_000,
    50_000,
    62_000,
    83_000,
    100_000,
    125_000,
    250_000,
    500_000,
    1_000_000,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CRT passive Kvaser session recorder",
    )
    parser.add_argument("--channel", type=int, default=0, help="Kvaser channel number")
    parser.add_argument(
        "--bitrate",
        type=int,
        choices=_BITRATES,
        default=250_000,
        help="CAN bitrate in bit/s",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="capture duration in seconds; 0 means until Ctrl+C",
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in KvaserReceiveMode],
        default=KvaserReceiveMode.BENCH.value,
        help="bench acknowledges frames; listen-only uses hardware silent mode",
    )
    parser.add_argument("--name", default="", help="optional session name")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("sessions"),
        help="directory for CRT and CSV output files",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="print every captured frame; disabled by default to avoid terminal overhead",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.duration < 0:
        raise SystemExit("--duration cannot be negative")

    channels = list_channels()
    channel_info = next((item for item in channels if item.number == args.channel), None)
    if channel_info is None:
        available = ", ".join(str(item.number) for item in channels) or "none"
        raise SystemExit(
            f"Kvaser channel {args.channel} was not found; available: {available}"
        )

    mode = KvaserReceiveMode(args.mode)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    requested_name = args.name.strip() or f"capture_{timestamp}"
    safe_name = _safe_filename(requested_name)

    session = CaptureSession(
        name=requested_name,
        source="kvaser-live",
        bitrate=args.bitrate,
        channel=args.channel,
        adapter=channel_info.name,
        metadata={
            "receive_mode": mode.value,
            "serial_number": channel_info.serial_number,
            "product_number": channel_info.product_number,
            "requested_duration_s": args.duration,
        },
    )

    print("CRT — rejestrator sesji CAN")
    print(f"Adapter: {channel_info.name}")
    print(f"Kanał: {args.channel}")
    print(f"Bitrate: {args.bitrate} bit/s")
    print(f"Tryb: {mode.value}")
    print(f"Sesja: {requested_name}")
    print("Zatrzymanie ręczne: Ctrl+C")
    print()

    started_monotonic = monotonic()
    capture_origin_ns = perf_counter_ns()
    deadline = None if args.duration == 0 else started_monotonic + args.duration
    next_status = started_monotonic + 1.0
    unique_ids: set[tuple[int, bool]] = set()

    try:
        with KvaserPassiveChannel(
            channel_number=args.channel,
            bitrate=args.bitrate,
            mode=mode,
        ) as channel:
            print("Kanał otwarty. Rejestracja rozpoczęta...")

            while deadline is None or monotonic() < deadline:
                frame = channel.read(timeout_ms=100)
                now = monotonic()

                if frame is not None:
                    normalized = replace(
                        frame,
                        timestamp_ns=max(0, frame.timestamp_ns - capture_origin_ns),
                    )
                    session.append(normalized)
                    unique_ids.add(
                        (normalized.arbitration_id, normalized.is_extended_id)
                    )
                    if args.live:
                        _print_frame(normalized)

                if not args.live and now >= next_status:
                    elapsed = now - started_monotonic
                    print(
                        f"{elapsed:7.1f} s | ramki: {len(session.frames):8d} | "
                        f"CAN ID: {len(unique_ids):4d}"
                    )
                    next_status = now + 1.0
    except KeyboardInterrupt:
        print("\nRejestracja zatrzymana przez użytkownika.")

    elapsed_s = monotonic() - started_monotonic
    session.metadata.update(
        {
            "actual_duration_s": round(elapsed_s, 6),
            "frame_count": len(session.frames),
            "unique_can_ids": len(unique_ids),
        }
    )

    frame_statistics = SessionAnalyzer().summarize(session.frames)
    transport_messages = TransportPipeline().process(session.frames)
    decoded_messages = ProtocolRegistry().decode_all(transport_messages)
    message_statistics = LogicalMessageAnalyzer().summarize(decoded_messages)

    session.metadata.update(
        {
            "logical_message_count": len(decoded_messages),
            "complete_logical_messages": sum(
                item.message.complete for item in decoded_messages
            ),
            "incomplete_logical_messages": sum(
                not item.message.complete for item in decoded_messages
            ),
        }
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    session_path = args.output_dir / f"{safe_name}.crt.jsonl"
    frames_path = args.output_dir / f"{safe_name}.frames.csv"
    summary_path = args.output_dir / f"{safe_name}.summary.csv"
    messages_path = args.output_dir / f"{safe_name}.messages.csv"
    message_summary_path = args.output_dir / f"{safe_name}.messages.summary.csv"

    save_session(session, session_path)
    save_frames_csv(session.frames, frames_path)
    save_summary_csv(frame_statistics, summary_path)
    save_messages_csv(decoded_messages, messages_path)
    save_message_summary_csv(message_statistics, message_summary_path)

    print()
    print("Rejestracja zakończona.")
    print(f"Czas: {elapsed_s:.3f} s")
    print(f"Ramki: {len(session.frames)}")
    print(f"Unikalne CAN ID: {len(frame_statistics)}")
    print(f"Wiadomości logiczne: {len(decoded_messages)}")
    print(
        "Wiadomości niekompletne: "
        f"{sum(not item.message.complete for item in decoded_messages)}"
    )
    print(f"Sesja CRT: {session_path}")
    print(f"Surowe CSV: {frames_path}")
    print(f"Podsumowanie ramek: {summary_path}")
    print(f"Wiadomości: {messages_path}")
    print(f"Podsumowanie wiadomości: {message_summary_path}")
    _print_summary(frame_statistics)
    _print_message_summary(message_statistics)
    return 0


def _print_frame(frame) -> None:
    id_width = 8 if frame.is_extended_id else 3
    frame_type = "EXT" if frame.is_extended_id else "STD"
    print(
        f"{frame.timestamp_ns / 1_000_000:12.3f} ms  "
        f"{frame_type}  ID=0x{frame.arbitration_id:0{id_width}X}  "
        f"DLC={frame.dlc}  DATA={frame.data_hex}"
    )


def _print_summary(statistics: list[CanIdStatistics]) -> None:
    if not statistics:
        print("Brak ramek do podsumowania.")
        return

    print()
    print("CAN ID       Typ   Ramki   Okres śr. [ms]   Częst. [Hz]   Zmienne bajty")
    print("-----------  ----  ------  ---------------  ------------  -------------")
    for item in statistics:
        id_width = 8 if item.is_extended_id else 3
        can_id = f"0x{item.arbitration_id:0{id_width}X}"
        frame_type = "EXT" if item.is_extended_id else "STD"
        period = "-" if item.mean_period_ms is None else f"{item.mean_period_ms:.3f}"
        frequency = (
            "-"
            if item.estimated_frequency_hz is None
            else f"{item.estimated_frequency_hz:.3f}"
        )
        changing = ",".join(
            str(index)
            for index, value in enumerate(item.changing_byte_mask)
            if value
        ) or "-"
        print(
            f"{can_id:<11}  {frame_type:<4}  {item.frame_count:>6}  "
            f"{period:>15}  {frequency:>12}  {changing}"
        )


def _print_message_summary(
    statistics: list[LogicalMessageStatistics],
) -> None:
    if not statistics:
        print("\nBrak wiadomości logicznych do podsumowania.")
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


def _safe_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return sanitized or "capture"


if __name__ == "__main__":
    raise SystemExit(main())
