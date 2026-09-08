from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from app.domain import Artifact, ArtifactSource

from ..contracts import AnalysisContext
from ..manifest import ExtensionManifest, ExtensionPermission, ExtensionType
from .signal_discovery import extract_bitfield, message_key_from_parameters


SIGNAL_PLOT_SERIES_PROVIDER_ID = "crt.analysis.signal_plot_series"
SIGNAL_PLOT_SERIES_PROVIDER_VERSION = "1.0.0"
SIGNAL_PLOT_SERIES_ALGORITHM_VERSION = "1"
SIGNAL_PLOT_SERIES_ARTIFACT_SCHEMA_VERSION = 1

DEFAULT_MAXIMUM_POINTS = 250_000
MAXIMUM_POINTS_LIMIT = 1_000_000
_PROGRESS_STRIDE = 4096


class SignalPlotSeriesProvider:
    """Build one complete exact-point signal series from one stored session."""

    manifest = ExtensionManifest(
        id=SIGNAL_PLOT_SERIES_PROVIDER_ID,
        name="Full Signal Plotter — pełna seria",
        version=SIGNAL_PLOT_SERIES_PROVIDER_VERSION,
        crt_api="1",
        type=ExtensionType.ANALYSIS,
        inputs=("session",),
        outputs=("signal_plot_series",),
        permissions=(
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.SESSION_READ,
            ExtensionPermission.ARTIFACT_WRITE,
        ),
    )
    algorithm_version = SIGNAL_PLOT_SERIES_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        analysis_input = _single_session_input(context)
        parameters = _parameters(analysis_input.parameters)
        key = message_key_from_parameters(parameters)
        source = context.project.session(analysis_input.source_id)
        expected_frames = source.frames.frame_count
        context.progress.report(0, expected_frames + 1, "budowanie pełnej serii sygnału")

        points: list[dict[str, Any]] = []
        matching_frame_count = 0
        field_missing_count = 0
        first_timestamp_ns: int | None = None
        last_timestamp_ns: int | None = None
        minimum_value: float | None = None
        maximum_value: float | None = None
        minimum_source_row: int | None = None
        maximum_source_row: int | None = None

        for source_row, frame in enumerate(source.frames.iter_frames()):
            if key.matches(frame):
                matching_frame_count += 1
                raw = extract_bitfield(
                    frame.data,
                    start_bit=parameters["start_bit"],
                    length=parameters["length"],
                    byte_order=parameters["byte_order"],
                    signed=parameters["signed"],
                )
                if raw is None:
                    field_missing_count += 1
                else:
                    if len(points) >= parameters["maximum_points"]:
                        raise ValueError(
                            "full signal series exceeds Stage 1 safety limit "
                            f"({parameters['maximum_points']} points); no partial artifact was written"
                        )
                    value = float(raw) * parameters["scale"] + parameters["offset"]
                    if not math.isfinite(value):
                        raise ValueError("scaled signal value is not finite")
                    point = {
                        "source_row": source_row,
                        "sequence": frame.sequence,
                        "timestamp_ns": frame.timestamp_ns,
                        "raw": raw,
                        "value": value,
                    }
                    points.append(point)
                    if first_timestamp_ns is None:
                        first_timestamp_ns = frame.timestamp_ns
                    last_timestamp_ns = frame.timestamp_ns
                    if minimum_value is None or value < minimum_value:
                        minimum_value = value
                        minimum_source_row = source_row
                    if maximum_value is None or value > maximum_value:
                        maximum_value = value
                        maximum_source_row = source_row

            processed = source_row + 1
            if processed % _PROGRESS_STRIDE == 0 or processed == expected_frames:
                context.cancellation.raise_if_cancelled()
                context.progress.report(
                    processed,
                    expected_frames + 1,
                    f"pełna seria: {processed}/{expected_frames} ramek, {len(points)} punktów",
                )

        context.cancellation.raise_if_cancelled()
        payload = {
            "schema": "crt.signal_plot_series",
            "schema_version": SIGNAL_PLOT_SERIES_ARTIFACT_SCHEMA_VERSION,
            "generated_by": {
                "provider_id": self.manifest.id,
                "provider_version": self.manifest.version,
                "algorithm_version": self.algorithm_version,
                "crt_api": self.manifest.crt_api,
            },
            "project": {
                "id": context.project.project_id,
                "name": context.project.project_name,
            },
            "session": {
                "id": source.id,
                "name": source.name,
                "sha256": source.sha256,
                "frame_count": source.frame_count,
            },
            "message_key": key.to_payload(),
            "bitfield": {
                "start_bit": parameters["start_bit"],
                "length": parameters["length"],
                "byte_order": parameters["byte_order"],
                "signed": parameters["signed"],
                "scale": parameters["scale"],
                "offset": parameters["offset"],
            },
            "series_contract": {
                "complete": True,
                "sampling": "none",
                "rendering_may_decimate": True,
                "cursor_selection_uses_full_series": True,
                "maximum_points_safety_limit": parameters["maximum_points"],
            },
            "summary": {
                "matching_frame_count": matching_frame_count,
                "point_count": len(points),
                "field_missing_count": field_missing_count,
                "first_timestamp_ns": first_timestamp_ns,
                "last_timestamp_ns": last_timestamp_ns,
                "minimum_value": minimum_value,
                "maximum_value": maximum_value,
                "minimum_source_row": minimum_source_row,
                "maximum_source_row": maximum_source_row,
            },
            "points": points,
        }
        artifact = context.artifact_writer.write_json(
            filename="signal-plot-series.json",
            artifact_type="signal_plot_series",
            schema_version=SIGNAL_PLOT_SERIES_ARTIFACT_SCHEMA_VERSION,
            sources=(
                ArtifactSource(
                    session_id=source.id,
                    source_kind="session",
                    source_reference={
                        "sha256": source.sha256,
                        "message_key": key.to_payload(),
                        "bitfield": payload["bitfield"],
                    },
                ),
            ),
            payload=payload,
            metadata={
                "session_id": source.id,
                "message_key": key.to_payload(),
                "bitfield": payload["bitfield"],
                "point_count": len(points),
                "series_complete": True,
                "sampling": "none",
            },
        )
        context.progress.report(expected_frames + 1, expected_frames + 1, "zapisano pełną serię sygnału")
        return artifact


def _single_session_input(context: AnalysisContext):
    if len(context.inputs) != 1 or context.inputs[0].kind != "session":
        raise ValueError("Full Signal Plotter requires exactly one session input")
    return context.inputs[0]


def _parameters(values: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(values)
    arbitration_id = values.get("arbitration_id")
    if isinstance(arbitration_id, str):
        arbitration_text = arbitration_id.strip()
        if not arbitration_text:
            raise ValueError("arbitration_id cannot be empty")
        # This provider backs a GUI field explicitly labelled CAN ID [hex]. Keep
        # Signal Discovery's shared parser unchanged, but make digit-only input here
        # unambiguously hexadecimal: "123" means CAN ID 0x123.
        if not arbitration_text.lower().startswith("0x"):
            arbitration_text = "0x" + arbitration_text
        result["arbitration_id"] = arbitration_text

    start_bit = int(values.get("start_bit", 0))
    length = int(values.get("length", 8))
    byte_order = str(values.get("byte_order", "intel")).strip().lower()
    signed = _parse_bool(values.get("signed", False))
    scale = float(values.get("scale", 1.0))
    offset = float(values.get("offset", 0.0))
    maximum_points = int(values.get("maximum_points", DEFAULT_MAXIMUM_POINTS))

    if start_bit < 0:
        raise ValueError("start_bit cannot be negative")
    if not 1 <= length <= 64:
        raise ValueError("length must be in range 1..64")
    if byte_order not in {"intel", "motorola"}:
        raise ValueError("byte_order must be intel or motorola")
    if not math.isfinite(scale) or not math.isfinite(offset):
        raise ValueError("scale and offset must be finite")
    if not 1 <= maximum_points <= MAXIMUM_POINTS_LIMIT:
        raise ValueError(
            f"maximum_points must be in range 1..{MAXIMUM_POINTS_LIMIT}"
        )

    result.update(
        {
            "start_bit": start_bit,
            "length": length,
            "byte_order": byte_order,
            "signed": signed,
            "scale": scale,
            "offset": offset,
            "maximum_points": maximum_points,
        }
    )
    return result


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


__all__ = [
    "DEFAULT_MAXIMUM_POINTS",
    "MAXIMUM_POINTS_LIMIT",
    "SIGNAL_PLOT_SERIES_ALGORITHM_VERSION",
    "SIGNAL_PLOT_SERIES_ARTIFACT_SCHEMA_VERSION",
    "SIGNAL_PLOT_SERIES_PROVIDER_ID",
    "SIGNAL_PLOT_SERIES_PROVIDER_VERSION",
    "SignalPlotSeriesProvider",
]
