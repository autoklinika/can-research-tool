from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .comparison_analysis_service import (
    ComparisonAnalysisExecutionResult,
    ComparisonAnalysisService,
)
from .domain import Artifact
from .extensions import ExtensionRegistry
from .extensions.builtin import (
    register_builtin_comparison_extensions,
    register_builtin_extensions,
)
from .extensions.builtin.signal_candidate_engine import (
    SIGNAL_CANDIDATE_ENGINE_PROVIDER_ID,
    SignalCandidateEngineProvider,
)
from .project import CrtProject


@dataclass(frozen=True, slots=True)
class SignalCandidateInputSelection:
    experiment_artifacts: tuple[Artifact, ...]
    signal_discovery_artifacts: tuple[Artifact, ...]
    candidate_message_keys: tuple[str, ...]


class SignalCandidateService:
    """Select stable deterministic artifacts and run Signal Candidate Engine."""

    def __init__(self, project: CrtProject) -> None:
        self.project = project
        registry = ExtensionRegistry(passive_only=True, ai_enabled=False)
        register_builtin_extensions(registry)
        register_builtin_comparison_extensions(registry)
        registry.register(SignalCandidateEngineProvider())
        self.analysis = ComparisonAnalysisService(project, registry=registry)

    def select_inputs(self, comparison_set_id: str) -> SignalCandidateInputSelection:
        comparison = self.analysis.comparison_sets.get(comparison_set_id)
        experiments: list[Artifact] = []
        experiment_signatures: set[str] = set()
        candidate_message_keys: set[str] = set()

        # Catalog order is newest first. Keep only the newest artifact for one
        # semantic Experiment Diff configuration so repeated manual re-runs do
        # not overweight the same experiment.
        for artifact in self.analysis.list_artifacts(comparison_set_id):
            if artifact.artifact_type != "experiment_marker_correlation":
                continue
            payload = self.analysis.artifacts.read_json(artifact)
            if payload.get("schema") != "crt.experiment_marker_correlation":
                continue
            comparison_payload = payload.get("comparison_set")
            if not isinstance(comparison_payload, dict):
                continue
            if str(comparison_payload.get("id", "")) != comparison.id:
                continue
            signature = _experiment_signature(payload)
            if signature in experiment_signatures:
                continue
            experiment_signatures.add(signature)
            experiments.append(artifact)
            rows = payload.get("ranked_candidates")
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict):
                        message_key = str(row.get("message_key", "")).strip()
                        if message_key:
                            candidate_message_keys.add(message_key)

        if not experiments:
            raise ValueError(
                "Brak artefaktu Experiment Diff dla tego zestawu. "
                "Najpierw wykonaj co najmniej jeden eksperyment marker correlation."
            )

        discovery: list[Artifact] = []
        seen_activity: set[tuple[str, str]] = set()
        for session_id in comparison.session_ids:
            for artifact in self.analysis.artifacts.list_for_session(session_id):
                if artifact.artifact_type != "signal_discovery_activity":
                    continue
                message_key = _discovery_message_key_from_metadata(artifact)
                if not message_key or message_key not in candidate_message_keys:
                    continue
                identity = (session_id, message_key)
                if identity in seen_activity:
                    continue
                seen_activity.add(identity)
                discovery.append(artifact)

        return SignalCandidateInputSelection(
            experiment_artifacts=tuple(experiments),
            signal_discovery_artifacts=tuple(discovery),
            candidate_message_keys=tuple(sorted(candidate_message_keys)),
        )

    def run(
        self,
        comparison_set_id: str,
        *,
        maximum_candidates: int = 500,
        maximum_evidence_events_per_candidate: int = 64,
        cancellation=None,
        progress_callback=None,
    ) -> ComparisonAnalysisExecutionResult:
        selection = self.select_inputs(comparison_set_id)
        return self.analysis.run(
            SIGNAL_CANDIDATE_ENGINE_PROVIDER_ID,
            comparison_set_id,
            parameters={
                "experiment_artifact_ids": [
                    artifact.id for artifact in selection.experiment_artifacts
                ],
                "signal_discovery_artifact_ids": [
                    artifact.id for artifact in selection.signal_discovery_artifacts
                ],
                "maximum_candidates": int(maximum_candidates),
                "maximum_evidence_events_per_candidate": int(
                    maximum_evidence_events_per_candidate
                ),
            },
            cancellation=cancellation,
            progress_callback=progress_callback,
        )

    def list_artifacts(self, comparison_set_id: str) -> tuple[Artifact, ...]:
        return tuple(
            artifact
            for artifact in self.analysis.list_artifacts(comparison_set_id)
            if artifact.artifact_type == "signal_candidates"
        )

    def read_artifact(self, artifact: Artifact) -> dict[str, Any]:
        payload = self.analysis.artifacts.read_json(artifact)
        return dict(payload)


def _experiment_signature(payload: dict[str, Any]) -> str:
    selection = payload.get("marker_selection")
    selection = selection if isinstance(selection, dict) else {}
    target = selection.get("target")
    target = target if isinstance(target, dict) else {}
    control = selection.get("control")
    control = control if isinstance(control, dict) else {}
    semantic = {
        "target_selector": target.get("selector", ""),
        "control_selector": control.get("selector", ""),
        "pre_window_ms": selection.get("pre_window_ms"),
        "post_window_ms": selection.get("post_window_ms"),
    }
    return json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _discovery_message_key_from_metadata(artifact: Artifact) -> str:
    metadata = artifact.metadata
    key = metadata.get("message_key") if isinstance(metadata, dict) else None
    if not isinstance(key, dict):
        return ""
    try:
        channel = int(key.get("channel", 0))
        arbitration_id = int(key.get("arbitration_id", 0))
        extended = bool(key.get("is_extended_id", False))
        frame_kind = str(key.get("frame_kind", "data")).strip().lower()
    except (TypeError, ValueError):
        return ""
    width = 8 if extended else 3
    return f"{channel}:{'EXT' if extended else 'STD'}:{arbitration_id:0{width}X}:{frame_kind}"


__all__ = ["SignalCandidateInputSelection", "SignalCandidateService"]
