from __future__ import annotations

from collections.abc import Mapping
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
from .extensions.builtin.signal_hypothesis_ai import (
    SIGNAL_HYPOTHESIS_PROVIDER_ID,
    SignalHypothesisAIProvider,
)
from .local_ai import LocalAIClient, LocalAIConfig, OpenAICompatibleLocalClient
from .project import CrtProject


class SignalHypothesisService:
    """Generate and read non-authoritative hypotheses for Signal Candidates."""

    def __init__(
        self,
        project: CrtProject,
        *,
        ai_client: LocalAIClient,
    ) -> None:
        self.project = project
        self.ai_client = ai_client
        registry = ExtensionRegistry(passive_only=True, ai_enabled=True)
        register_builtin_extensions(registry)
        register_builtin_comparison_extensions(registry)
        registry.register(SignalHypothesisAIProvider())
        self.analysis = ComparisonAnalysisService(
            project,
            registry=registry,
            ai_client=ai_client,
        )

    @classmethod
    def from_config(
        cls,
        project: CrtProject,
        config: LocalAIConfig,
    ) -> "SignalHypothesisService":
        return cls(project, ai_client=OpenAICompatibleLocalClient(config))

    def list_candidate_artifacts(self, comparison_set_id: str) -> tuple[Artifact, ...]:
        return tuple(
            artifact
            for artifact in self.analysis.list_artifacts(comparison_set_id)
            if artifact.artifact_type == "signal_candidates"
        )

    def candidate_rows(self, artifact: Artifact) -> tuple[dict[str, Any], ...]:
        payload = self.analysis.artifacts.read_json(artifact)
        if payload.get("schema") != "crt.signal_candidates":
            raise ValueError("wybrany artefakt nie jest Signal Candidates")
        rows = payload.get("candidates")
        if not isinstance(rows, list):
            return ()
        return tuple(dict(item) for item in rows if isinstance(item, Mapping))

    def run(
        self,
        comparison_set_id: str,
        *,
        candidate_artifact_id: str,
        candidate_key: str,
        user_context: str = "",
        maximum_evidence_events: int = 8,
        cancellation=None,
        progress_callback=None,
    ) -> ComparisonAnalysisExecutionResult:
        return self.analysis.run(
            SIGNAL_HYPOTHESIS_PROVIDER_ID,
            comparison_set_id,
            parameters={
                "candidate_artifact_id": candidate_artifact_id,
                "candidate_key": candidate_key,
                "user_context": user_context,
                "maximum_evidence_events": int(maximum_evidence_events),
            },
            cancellation=cancellation,
            progress_callback=progress_callback,
        )

    def list_hypothesis_artifacts(self, comparison_set_id: str) -> tuple[Artifact, ...]:
        return tuple(
            artifact
            for artifact in self.analysis.list_artifacts(comparison_set_id)
            if artifact.artifact_type == "signal_hypothesis"
        )

    def read_hypothesis(self, artifact: Artifact) -> dict[str, Any]:
        payload = self.analysis.artifacts.read_json(artifact)
        return dict(payload)


__all__ = ["SignalHypothesisService"]
