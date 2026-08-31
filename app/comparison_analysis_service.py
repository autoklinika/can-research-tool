from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .artifact_catalog import ArtifactCatalog
from .comparison_sets import ComparisonSetStore
from .domain import AnalysisInput, Artifact
from .extensions import (
    AnalysisContext,
    ArtifactWriter,
    CancellationToken,
    ComparisonContext,
    ExtensionManifest,
    ExtensionPermission,
    ExtensionRegistry,
    ExtensionRunner,
    ExtensionType,
    FindingWriter,
    ProgressReporter,
    ProgressUpdate,
    ProjectContext,
)
from .extensions.builtin import (
    register_builtin_comparison_extensions,
    register_builtin_extensions,
)
from .project import CrtProject
from .project_domain_store import ProjectDomainStore


@dataclass(frozen=True, slots=True)
class ComparisonAnalysisExecutionResult:
    analysis_run_id: str
    provider_id: str
    comparison_set_id: str
    artifacts: tuple[Artifact, ...]


class ComparisonAnalysisService:
    """Application layer for deterministic passive analysis of comparison sets."""

    def __init__(
        self,
        project: CrtProject,
        *,
        registry: ExtensionRegistry | None = None,
    ) -> None:
        self.project = project
        self.store = ProjectDomainStore(project)
        self.comparison_sets = ComparisonSetStore(project)
        if registry is None:
            registry = ExtensionRegistry(passive_only=True, ai_enabled=False)
            register_builtin_extensions(registry)
            register_builtin_comparison_extensions(registry)
        self.registry = registry
        self.runner = ExtensionRunner(registry=registry, store=self.store)
        self.artifacts = ArtifactCatalog(project)

    def available_comparison_analyses(self) -> tuple[ExtensionManifest, ...]:
        return self.registry.manifests(
            extension_type=ExtensionType.COMPARISON,
            input_kind="comparison_set",
        )

    def run(
        self,
        provider_id: str,
        comparison_set_id: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        cancellation: CancellationToken | None = None,
        progress_callback: Callable[[ProgressUpdate], None] | None = None,
    ) -> ComparisonAnalysisExecutionResult:
        cleaned_comparison_set_id = comparison_set_id.strip()
        if not cleaned_comparison_set_id:
            raise ValueError("comparison_set_id cannot be empty")
        provider = self.registry.get_comparison(provider_id)
        manifest = provider.manifest
        if "comparison_set" not in manifest.inputs:
            raise ValueError(f"provider does not accept comparison_set input: {manifest.id}")

        comparison = self.comparison_sets.get(cleaned_comparison_set_id)
        normalized_parameters = dict(comparison.parameters)
        normalized_parameters.update(parameters or {})
        analysis_input = AnalysisInput(
            kind="comparison_set",
            source_id=comparison.id,
            parameters=normalized_parameters,
        )
        algorithm_version = str(
            getattr(provider, "algorithm_version", manifest.version)
        ).strip()
        if not algorithm_version:
            raise ValueError(f"provider algorithm version is empty: {manifest.id}")

        run = self.store.create_analysis_run(
            provider_id=manifest.id,
            provider_version=manifest.version,
            algorithm_version=algorithm_version,
            inputs=(analysis_input,),
            parameters=normalized_parameters,
            crt_api_version=manifest.crt_api,
        )
        token = cancellation or CancellationToken()
        progress = ProgressReporter(progress_callback)
        context = AnalysisContext(
            project=ProjectContext(
                self.project,
                token,
                artifact_read_enabled=(
                    ExtensionPermission.ARTIFACT_READ in manifest.permissions
                ),
            ),
            analysis_run_id=run.id,
            inputs=(analysis_input,),
            cancellation=token,
            progress=progress,
            artifact_writer=ArtifactWriter(
                project=self.project,
                store=self.store,
                analysis_run_id=run.id,
                provider_id=run.provider_id,
                provider_version=run.provider_version,
                algorithm_version=run.algorithm_version,
                cancellation=token,
            ),
            finding_writer=FindingWriter(
                store=self.store,
                cancellation=token,
                algorithm_id=run.provider_id,
                algorithm_version=run.algorithm_version,
            ),
            comparison=ComparisonContext(
                id=comparison.id,
                name=comparison.name,
                session_ids=comparison.session_ids,
                base_session_id=comparison.base_session_id,
                synchronization_mode=comparison.synchronization_mode,
                parameters=dict(comparison.parameters),
            ),
        )
        result = self.runner.execute_comparison(manifest.id, context)
        return ComparisonAnalysisExecutionResult(
            analysis_run_id=run.id,
            provider_id=manifest.id,
            comparison_set_id=comparison.id,
            artifacts=_normalize_artifacts(result),
        )

    def list_artifacts(self, comparison_set_id: str) -> tuple[Artifact, ...]:
        return self.artifacts.list_for_comparison_set(comparison_set_id)


def _normalize_artifacts(result: object) -> tuple[Artifact, ...]:
    if isinstance(result, Artifact):
        return (result,)
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        artifacts = tuple(item for item in result if isinstance(item, Artifact))
        if len(artifacts) != len(result):
            raise TypeError("analysis result sequence contains a non-artifact value")
        if artifacts:
            return artifacts
    raise TypeError("analysis provider did not return an artifact")


__all__ = [
    "ComparisonAnalysisExecutionResult",
    "ComparisonAnalysisService",
]
