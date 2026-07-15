from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from .models import CanFrame, FrameDirection


@dataclass(frozen=True, slots=True)
class CsvImportResult:
    frames: list[CanFrame]
    warnings: list[str]


def import_can_csv(path: str | Path) -> CsvImportResult:
    source = Path(path)
    warnings: list[str] = []
    frames: list[CanFrame] = []

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("CSV file does not contain a header")

        columns = {_normalize(name): name for name in reader.fieldnames if name is not None}
        timestamp_column = _find_column(columns, "timestamp", "time", "times", "timeoffset")
        id_column = _find_column(columns, "id", "canid", "identifier", "messageid")
        data_column = _find_column(columns, "data", "payload", "bytes", required=False)
        channel_column = _find_column(columns, "channel", "ch", required=False)
        direction_column = _find_column(columns, "direction", "dir", required=False)

        for line_number, row in enumerate(reader, start=2):
            try:
                timestamp_s = _parse_timestamp(row.get(timestamp_column, ""))
                arbitration_id = _parse_can_id(row.get(id_column, ""))
                data = _parse_data(row.get(data_column, "")) if data_column else _parse_data_bytes(row)
                channel = (row.get(channel_column, "") if channel_column else "").strip()
                direction = _parse_direction(row.get(direction_column, "") if direction_column else "")
                frames.append(
                    CanFrame(
                        timestamp_s=timestamp_s,
                        arbitration_id=arbitration_id,
                        data=data,
                        channel=channel,
                        direction=direction,
                    )
                )
            except (TypeError, ValueError) as exc:
                warnings.append(f"Line {line_number}: {exc}")

    return CsvImportResult(frames=frames, warnings=warnings)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _find_column(
    columns: dict[str, str], *candidates: str, required: bool = True
) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return columns[candidate]
    if required:
        raise ValueError(f"Missing required CSV column: one of {', '.join(candidates)}")
    return None


def _parse_timestamp(raw: str | None) -> float:
    value = (raw or "").strip().replace(",", ".")
    if not value:
        raise ValueError("empty timestamp")
    try:
        return float(value)
    except ValueError:
        parts = value.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        raise ValueError(f"invalid timestamp {value!r}") from None


def _parse_can_id(raw: str | None) -> int:
    value = (raw or "").strip().upper().replace("0X", "")
    value = value.removesuffix("X").strip()
    if not value:
        raise ValueError("empty CAN ID")
    base = 16 if any(char in "ABCDEF" for char in value) or len(value) > 3 else 10
    arbitration_id = int(value, base)
    if not 0 <= arbitration_id <= 0x1FFFFFFF:
        raise ValueError(f"CAN ID out of range: {value}")
    return arbitration_id


def _parse_data(raw: str | None) -> bytes:
    value = (raw or "").strip()
    if not value:
        return b""
    tokens = re.findall(r"(?i)(?:0x)?([0-9a-f]{2})", value)
    if not tokens:
        raise ValueError(f"invalid CAN data {value!r}")
    return bytes(int(token, 16) for token in tokens)


def _parse_data_bytes(row: dict[str, str]) -> bytes:
    indexed: list[tuple[int, int]] = []
    for key, raw_value in row.items():
        match = re.fullmatch(r"(?i)(?:data|byte|b)(\d+)", _normalize(key or ""))
        if match and (raw_value or "").strip():
            indexed.append((int(match.group(1)), int((raw_value or "").strip(), 16)))
    indexed.sort()
    return bytes(value for _, value in indexed)


def _parse_direction(raw: str) -> FrameDirection:
    value = raw.strip().lower()
    if value in {"rx", "receive", "received"}:
        return FrameDirection.RX
    if value in {"tx", "transmit", "transmitted"}:
        return FrameDirection.TX
    return FrameDirection.UNKNOWN
