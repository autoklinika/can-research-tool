from __future__ import annotations

import argparse
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from time import monotonic, perf_counter_ns

from app.analysis import CanIdStatistics, SessionAnalyzer
from app.exports import save_frames_csv, save_summary_csv
from app.models import CaptureSession
from app.session_io import save_session
from kvaser.backend import (
    KvaserPassiveChannel,
    KvaserReceiveMode,
    list_channels,
)


_BITRATES = (10_000, 50_000, 62_000, 83_000, 100_000, 125_000, 250_000, 500_000, 1_000_000)


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
        help="directory for CRT, raw CSV and summary files",
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
        raise SystemExit(f"Kvaser channel {args.channel} was not found; available: {available}")

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
                    unique_ids.add((normalized.arbitration_id, normalized.is_extended_id))
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

    statistics = SessionAnalyzer().summarize(session.frames)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    session_path = args.output_dir / f"{safe_name}.crt.jsonl"
    frames_path = args.output_dir / f"{safe_name}.frames.csv"
    summary_path = args.output_dir / f"{safe_name}.summary.csv"

    save_session(session, session_path)
    save_frames_csv(session.frames, frames_path)
    save_summary_csv(statistics, summary_path)

    print()
    print("Rejestracja zakończona.")
    print(f"Czas: {elapsed_s:.3f} s")
    print(f"Ramki: {len(session.frames)}")
    print(f"Unikalne CAN ID: {len(statistics)}")
    print(f"Sesja CRT: {session_path}")
    print(f"Surowe CSV: {frames_path}")
    print(f"Podsumowanie: {summary_path}")
    _print_summary(statistics)
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
            "-" if item.estimated_frequency_hz is None else f"{item.estimated_frequency_hz:.3f}"
        )
        changing = ",".join(
            str(index) for index, value in enumerate(item.changing_byte_mask) if value
        ) or "-"
        print(
            f"{can_id:<11}  {frame_type:<4}  {item.frame_count:>6}  "
            f"{period:>15}  {frequency:>12}  {changing}"
        )


def _safe_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return sanitized or "capture"


if __name__ == "__main__":
    raise SystemExit(main())
