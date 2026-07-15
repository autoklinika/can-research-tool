from __future__ import annotations

from time import monotonic

from kvaser.backend import KvaserPassiveChannel, KvaserReceiveMode


CHANNEL = 0
BITRATE = 250_000
CAPTURE_TIME_SECONDS = 10


def main() -> None:
    frame_count = 0

    print("CRT — pasywny test Kvaser")
    print(f"Kanał: {CHANNEL}")
    print(f"Bitrate: {BITRATE} bit/s")
    print("Tryb: BENCH — CRT nie nadaje ramek, ACK aktywny")
    print()

    with KvaserPassiveChannel(
        channel_number=CHANNEL,
        bitrate=BITRATE,
        mode=KvaserReceiveMode.BENCH,
    ) as can_channel:
        print("Kanał otwarty. Nasłuch rozpoczęty...")

        stop_time = monotonic() + CAPTURE_TIME_SECONDS

        while monotonic() < stop_time:
            frame = can_channel.read(timeout_ms=100)
            if frame is None:
                continue

            frame_count += 1
            id_width = 8 if frame.is_extended_id else 3
            frame_type = "EXT" if frame.is_extended_id else "STD"

            print(
                f"{frame.sequence:06d}  "
                f"{frame_type}  "
                f"ID=0x{frame.arbitration_id:0{id_width}X}  "
                f"DLC={frame.dlc}  "
                f"DATA={frame.data_hex}"
            )

    print()
    print(f"Nasłuch zakończony. Liczba ramek: {frame_count}")


if __name__ == "__main__":
    main()
