from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from app.models import CanFrame, CaptureSession


_REQUIRED_COLUMNS = {"timestamp", "can_id", "type", "dlc", "data"}


@dataclass(frozen=True, slots=True)
class KvaserCsvImportResult:
    session: CaptureSession
    warnings: tuple[str, ...]


def import_monitor_csv(path: str | Path, *, channel: int = 0) -> KvaserCsvImportResult:
    """Import CSV files produced by the existing Kvaser monitor.

    The monitor stores CANlib ``frame.timestamp`` values. CANlib uses millisecond
    timestamps by default, so CRT normalizes them to nanoseconds relative to the
    first imported frame while preserving the original value in ``source_timestamp``.
    """

    source = Path(path)
    warnings: list[str] = []
    session = CaptureSession(
        name=source.stem,
        source="kvaser-monitor-csv",
        channel=channel,
        metadata={"source_path": str(source), "timestamp_unit": "ms"},
    )

    first_source_timestamp: int | None = None
    for frame, frame_warnings in iter_monitor_csv(source, channel=channel):
        warnings.extend(frame_warnings)
        if first_source_timestamp is None:
            first_source_timestamp = frame.source_timestamp
        session.append(frame)

    session.metadata["warning_count"] = len(warnings)
    session.metadata["frame_count"] = len(session.frames)
    return KvaserCsvImportResult(session=session, warnings=tuple(warnings))


def iter_monitor_csv(
    path: str | Path, *, channel: int = 0
) -> Iterator[tuple[CanFrame, tuple[str, ...]]]:
    source = Path(path)

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if reader.fieldnames is None:
            raise ValueError("Kvaser CSV does not contain a header")

        normalized = {name.strip().lower(): name for name in reader.fieldnames if name}
        missing = _REQUIRED_COLUMNS - normalized.keys()
        if missing:
            raise ValueError(
                "Unsupported Kvaser CSV header; missing columns: " + ", ".join(sorted(missing))
            )

        first_timestamp: int | None = None
        sequence = 0

        for line_number, row in enumerate(reader, start=2):
            row_warnings: list[str] = []
            try:
                source_timestamp = _parse_timestamp(row[normalized["timestamp"]])
                if first_timestamp is None:
                    first_timestamp = source_timestamp
                timestamp_ns = (source_timestamp - first_timestamp) * 1_000_000

                type_text = (row[normalized["type"]] or "").strip().upper()
                arbitration_id = _parse_can_id(row[normalized["can_id"]])
                data = _parse_data(row[normalized["data"]])
                declared_dlc = int((row[normalized["dlc"]] or "0").strip())

                if declared_dlc != len(data):
                    row_warnings.append(
                        f"line {line_number}: DLC={declared_dlc}, parsed data length={len(data)}"
                    )

                is_extended = "EXT" in type_text or arbitration_id > 0x7FF
                is_remote = "RTR" in type_text
                is_error = "ERR" in type_text

                frame = CanFrame(
                    sequence=sequence,
                    timestamp_ns=timestamp_ns,
                    arbitration_id=arbitration_id,
                    data=data,
                    channel=channel,
                    is_extended_id=is_extended,
                    is_remote_frame=is_remote,
                    is_error_frame=is_error,
                    source_timestamp=source_timestamp,
                )
                sequence += 1
                yield frame, tuple(row_warnings)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid Kvaser CSV row at line {line_number}: {exc}") from exc


def _parse_timestamp(raw: str | None) -> int:
    value = (raw or "").strip()
    if not value:
        raise ValueError("empty timestamp")
    return int(value, 10)


def _parse_can_id(raw: str | None) -> int:
    value = (raw or "").strip().upper().removeprefix("0X")
    if not value:
        raise ValueError("empty CAN ID")
    arbitration_id = int(value, 16)
    if not 0 <= arbitration_id <= 0x1FFFFFFF:
        raise ValueError(f"CAN ID outside 29-bit range: {value}")
    return arbitration_id


def _parse_data(raw: str | None) -> bytes:
    value = (raw or "").strip()
    if not value:
        return b""

    tokens = value.replace(",", " ").split()
    try:
        data = bytes(int(token.removeprefix("0x").removeprefix("0X"), 16) for token in tokens)
    except ValueError as exc:
        raise ValueError(f"invalid DATA field: {value!r}") from exc

    if len(data) > 64:
        raise ValueError("CAN payload exceeds 64 bytes")
    return data
