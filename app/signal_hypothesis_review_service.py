from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifact_catalog import ArtifactCatalog
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
from .extensions.builtin.signal_hypothesis_review import (
    SIGNAL_HYPOTHESIS_REVIEW_ARTIFACT_SCHEMA_VERSION,
    SIGNAL_HYPOTHESIS_REVIEW_PROVIDER_ID,
    SignalHypothesisReviewProvider,
)
from .project import CrtProject


class SignalHypothesisReviewService:
    """Append-only operator review workflow for Signal Hypothesis artifacts."""

    def __init__(self, project: CrtProject) -> None:
        self.project = project
        self.artifacts = ArtifactCatalog(project)

    def run(
        self,
        comparison_set_id: str,
        *,
        hypothesis_artifact_id: str,
        action: str,
        operator_hypothesis: Mapping[str, Any] | None = None,
        operator_note: str = "",
        cancellation=None,
        progress_callback=None,
    ) -> ComparisonAnalysisExecutionResult:
        registry = ExtensionRegistry(passive_only=True, ai_enabled=False)
        register_builtin_extensions(registry)
        register_builtin_comparison_extensions(registry)
        registry.register(SignalHypothesisReviewProvider())
        analysis = ComparisonAnalysisService(self.project, registry=registry)
        return analysis.run(
            SIGNAL_HYPOTHESIS_REVIEW_PROVIDER_ID,
            comparison_set_id,
            parameters={
                "hypothesis_artifact_id": hypothesis_artifact_id,
                "action": action,
                "operator_hypothesis": dict(operator_hypothesis or {}),
                "operator_note": operator_note,
            },
            cancellation=cancellation,
            progress_callback=progress_callback,
        )

    def list_review_artifacts(
        self,
        comparison_set_id: str,
        *,
        hypothesis_artifact_id: str = "",
    ) -> tuple[Artifact, ...]:
        selected = hypothesis_artifact_id.strip()
        result: list[Artifact] = []
        for artifact in self.artifacts.list_for_comparison_set(comparison_set_id):
            if artifact.artifact_type != "signal_hypothesis_review":
                continue
            if artifact.schema_version != SIGNAL_HYPOTHESIS_REVIEW_ARTIFACT_SCHEMA_VERSION:
                continue
            if selected and str(artifact.metadata.get("hypothesis_artifact_id", "")) != selected:
                continue
            result.append(artifact)
        return tuple(result)

    def latest_review(
        self,
        comparison_set_id: str,
        hypothesis_artifact_id: str,
    ) -> Artifact | None:
        artifacts = self.list_review_artifacts(
            comparison_set_id,
            hypothesis_artifact_id=hypothesis_artifact_id,
        )
        return artifacts[0] if artifacts else None

    def read_review(self, artifact: Artifact) -> dict[str, Any]:
        if artifact.artifact_type != "signal_hypothesis_review":
            raise ValueError("wybrany artefakt nie jest Signal Hypothesis Review")
        if artifact.schema_version != SIGNAL_HYPOTHESIS_REVIEW_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("nieobsługiwana wersja Signal Hypothesis Review")
        payload = self.artifacts.read_json(artifact)
        if payload.get("schema") != "crt.signal_hypothesis_review":
            raise ValueError("nieoczekiwany schemat Signal Hypothesis Review")
        if payload.get("schema_version") != SIGNAL_HYPOTHESIS_REVIEW_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("niespójna wersja schematu Signal Hypothesis Review")
        return dict(payload)


__all__ = ["SignalHypothesisReviewService"]
