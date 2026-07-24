from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any

STATUS_NEW = "Nowe"
STATUS_MISSING = "Brakujące"
STATUS_CHANGED = "Zmienione"
STATUS_UNCHANGED = "Bez zmian"

STATUS_ORDER = {
    STATUS_MISSING: 0,
    STATUS_NEW: 1,
    STATUS_CHANGED: 2,
    STATUS_UNCHANGED: 3,
}

SCHEMA_STATISTICS = "crt.comparison_statistics"
SCHEMA_PAYLOAD = "crt.payload_differences"
SCHEMA_SEQUENCE = "crt.message_sequence_differences"


@dataclass(slots=True)
class ComparisonVisualRow:
    session_id: str
    session_name: str
    message_key: str
    channel: int
    arbitration_id_hex: str
    is_extended_id: bool
    frame_kind: str
    status: str = STATUS_UNCHANGED
    baseline_frame_count: int | None = None
    current_frame_count: int | None = None
    baseline_frequency_hz: float | None = None
    current_frequency_hz: float | None = None
    frequency_delta_percent: float | None = None
    payload_change_count: int = 0
    payload_byte_indices: tuple[int, ...] = ()
    sequence_change_count: int = 0
    evidence_count: int = 0
    baseline_payload_profile: dict[str, Any] | None = None
    current_payload_profile: dict[str, Any] | None = None

    @property
    def display_key(self) -> str:
        frame_format = "EXT" if self.is_extended_id else "STD"
        return f"CH{self.channel} {frame_format} 0x{self.arbitration_id_hex}"

    @property
    def magnitude(self) -> float:
        return max(
            abs(self.frequency_delta_percent or 0.0),
            float(self.payload_change_count),
            float(self.sequence_change_count),
        )


@dataclass(slots=True)
class ComparisonDashboardData:
    comparison_name: str
    sessions: list[dict[str, Any]] = field(default_factory=list)
    rows: list[ComparisonVisualRow] = field(default_factory=list)
    new_count: int = 0
    missing_count: int = 0
    changed_payload_count: int = 0
    changed_sequence_count: int = 0
    largest_frequency_delta: float | None = None
    largest_frequency_key: str = ""
    artifact_schemas: tuple[str, ...] = ()


def build_dashboard_data(
    comparison_name: str,
    payloads: dict[str, dict[str, Any]],
) -> ComparisonDashboardData:
    data = ComparisonDashboardData(comparison_name)
    data.artifact_schemas = tuple(sorted(payloads))
    statistics = payloads.get(SCHEMA_STATISTICS, {})
    payload = payloads.get(SCHEMA_PAYLOAD, {})
    sequence = payloads.get(SCHEMA_SEQUENCE, {})
    data.sessions = _merge_sessions(statistics, payload, sequence)
    rows: dict[tuple[str, str], ComparisonVisualRow] = {}

    for item in dict_list(statistics.get("message_keys")):
        baseline = dict_or_none(item.get("baseline"))
        message_key = str(item.get("message_key") or "")
        for session_row in dict_list(item.get("sessions")):
            if session_row.get("role") == "base":
                continue
            current = dict_or_none(session_row.get("statistics"))
            change = dict_value(session_row.get("change"))
            reasons = [str(value) for value in list_value(change.get("reasons"))]
            row = ComparisonVisualRow(
                session_id=str(session_row.get("session_id") or ""),
                session_name=str(session_row.get("session_name") or "—"),
                message_key=message_key,
                channel=int_value(item.get("channel")),
                arbitration_id_hex=str(item.get("arbitration_id_hex") or "—"),
                is_extended_id=bool(item.get("is_extended_id")),
                frame_kind=str(item.get("frame_kind") or "data"),
                status=_status(baseline, current, reasons),
                baseline_frame_count=optional_int(get_value(baseline, "frame_count")),
                current_frame_count=optional_int(get_value(current, "frame_count")),
                baseline_frequency_hz=optional_float(
                    get_value(baseline, "mean_positive_frequency_hz")
                ),
                current_frequency_hz=optional_float(
                    get_value(current, "mean_positive_frequency_hz")
                ),
                frequency_delta_percent=optional_float(
                    change.get("frequency_delta_percent")
                ),
            )
            rows[(row.session_id, row.message_key)] = row

    for item in dict_list(payload.get("message_payload_profiles")):
        message_key = str(item.get("message_key") or "")
        baseline_profile = dict_or_none(item.get("baseline"))
        for session_row in dict_list(item.get("sessions")):
            if session_row.get("role") == "base":
                continue
            session_id = str(session_row.get("session_id") or "")
            key = (session_id, message_key)
            current_profile = dict_or_none(session_row.get("payload_profile"))
            changes = dict_list(session_row.get("comparison_to_baseline"))
            row = rows.get(key)
            if row is None:
                row = ComparisonVisualRow(
                    session_id=session_id,
                    session_name=str(session_row.get("session_name") or "—"),
                    message_key=message_key,
                    channel=int_value(item.get("channel")),
                    arbitration_id_hex=str(item.get("arbitration_id_hex") or "—"),
                    is_extended_id=bool(item.get("is_extended_id")),
                    frame_kind=str(item.get("frame_kind") or "data"),
                    status=_status(baseline_profile, current_profile, []),
                    baseline_frame_count=optional_int(
                        get_value(baseline_profile, "frame_count")
                    ),
                    current_frame_count=optional_int(
                        get_value(current_profile, "frame_count")
                    ),
                )
                rows[key] = row
            row.baseline_payload_profile = baseline_profile
            row.current_payload_profile = current_profile
            row.payload_change_count = len(changes)
            row.payload_byte_indices = tuple(
                sorted(
                    {
                        int_value(change.get("byte_index"))
                        for change in changes
                        if change.get("byte_index") is not None
                    }
                )
            )
            if changes and row.status == STATUS_UNCHANGED:
                row.status = STATUS_CHANGED

    sequence_changes = dict_list(sequence.get("ranked_changes"))
    data.changed_sequence_count = int_value(
        dict_value(sequence.get("summary")).get(
            "notable_change_count",
            len(sequence_changes),
        )
    )
    sequence_change_counts = _sequence_change_counts(sequence_changes)
    for row in rows.values():
        row.sequence_change_count = sequence_change_counts.get(row.message_key, 0)
        row.evidence_count = (
            int(row.status != STATUS_UNCHANGED)
            + row.payload_change_count
            + row.sequence_change_count
        )

    data.rows = list(rows.values())
    data.new_count = sum(1 for row in data.rows if row.status == STATUS_NEW)
    data.missing_count = sum(
        1 for row in data.rows if row.status == STATUS_MISSING
    )
    data.changed_payload_count = sum(
        1 for row in data.rows if row.payload_change_count > 0
    )
    frequency_rows = [
        row
        for row in data.rows
        if row.frequency_delta_percent is not None
        and isfinite(float(row.frequency_delta_percent))
    ]
    if frequency_rows:
        largest = max(
            frequency_rows,
            key=lambda row: abs(float(row.frequency_delta_percent or 0.0)),
        )
        data.largest_frequency_delta = largest.frequency_delta_percent
        data.largest_frequency_key = largest.display_key
    return data


def format_integer(value: int | None) -> str:
    return "—" if value is None else f"{value:,}".replace(",", " ")


def format_hz(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.3f}".rstrip("0").rstrip(".") + " Hz"


def format_percent(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%".replace(".", ",")


def short_key(value: str) -> str:
    parts = value.split(":")
    if len(parts) >= 4:
        return f"CH{parts[0]} {parts[1]} 0x{parts[2]}"
    return value


def payload_summary(row: ComparisonVisualRow) -> str:
    if row.payload_change_count <= 0:
        return "0"
    if not row.payload_byte_indices:
        return str(row.payload_change_count)
    positions = ", ".join(str(index) for index in row.payload_byte_indices[:8])
    suffix = "…" if len(row.payload_byte_indices) > 8 else ""
    return f"{row.payload_change_count} (B{positions}{suffix})"


def byte_positions(profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(profile, dict):
        return []
    return dict_list(profile.get("byte_positions"))


def dominant_value(positions: list[dict[str, Any]], index: int) -> str:
    if index >= len(positions):
        return "—"
    value = positions[index]
    if value.get("classification") == "absent":
        return "—"
    dominant = value.get("dominant_value_hex")
    if dominant is not None:
        return str(dominant)
    values = dict_list(value.get("values"))
    return str(values[0].get("value_hex")) if values else "?"


def byte_delta(baseline: str, current: str) -> str:
    try:
        delta = int(current, 16) - int(baseline, 16)
    except (TypeError, ValueError):
        return "≠"
    return f"{delta:+d}"


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def dict_or_none(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def list_value(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def get_value(value: dict[str, Any] | None, key: str) -> object:
    return None if value is None else value.get(key)


def int_value(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def optional_hex_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "—":
        return None
    try:
        return int(text, 16)
    except (TypeError, ValueError, OverflowError):
        return None


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _sequence_change_counts(
    changes: list[dict[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for change in changes:
        sequence_text = str(change.get("sequence_text") or "")
        message_keys = {
            token.strip()
            for token in sequence_text.split("→")
            if token.strip()
        }
        for message_key in message_keys:
            counts[message_key] = counts.get(message_key, 0) + 1
    return counts


def _merge_sessions(*payloads: dict[str, Any]) -> list[dict[str, Any]]:
    merged = {}
    order = []
    for payload in payloads:
        for session in dict_list(payload.get("sessions")):
            session_id = str(session.get("id") or "")
            if not session_id:
                continue
            if session_id not in merged:
                order.append(session_id)
                merged[session_id] = {
                    "id": session_id,
                    "name": str(session.get("name") or session_id),
                    "role": str(session.get("role") or "compared"),
                }
            elif session.get("role") == "base":
                merged[session_id]["role"] = "base"
    return [merged[session_id] for session_id in order]


def _status(
    baseline: dict[str, Any] | None,
    current: dict[str, Any] | None,
    reasons: list[str],
) -> str:
    if baseline is None and current is not None:
        return STATUS_NEW
    if baseline is not None and current is None:
        return STATUS_MISSING
    return STATUS_CHANGED if reasons else STATUS_UNCHANGED
