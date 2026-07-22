from __future__ import annotations

from app.domain import AnalysisStatus
from app.project_domain_store import ProjectDomainStore

from .contracts import AnalysisContext, ExtensionCancelled
from .registry import ExtensionRegistry


class ExtensionExecutionError(RuntimeError):
    def __init__(self, extension_id: str, message: str) -> None:
        super().__init__(f"extension {extension_id} failed: {message}")
        self.extension_id = extension_id


class ExtensionRunner:
    """Exception boundary and lifecycle controller for passive providers."""

    def __init__(
        self,
        *,
        registry: ExtensionRegistry,
        store: ProjectDomainStore,
    ) -> None:
        self._registry = registry
        self._store = store

    def execute_analysis(self, extension_id: str, context: AnalysisContext) -> object:
        provider = self._registry.get_analysis(extension_id)
        return self._execute(provider, context)

    def execute_comparison(self, extension_id: str, context: AnalysisContext) -> object:
        provider = self._registry.get_comparison(extension_id)
        return self._execute(provider, context)

    def _execute(self, provider: object, context: AnalysisContext) -> object:
        manifest = getattr(provider, "manifest")

        if context.cancellation.is_cancelled:
            self._store.set_analysis_status(
                context.analysis_run_id,
                AnalysisStatus.CANCELLED,
                error="cancelled before execution",
            )
            raise ExtensionCancelled("extension execution was cancelled")

        self._store.set_analysis_status(context.analysis_run_id, AnalysisStatus.RUNNING)
        try:
            result = provider.run(context)
            context.cancellation.raise_if_cancelled()
        except ExtensionCancelled:
            self._store.set_analysis_status(
                context.analysis_run_id,
                AnalysisStatus.CANCELLED,
                error="cancelled by user",
            )
            raise
        except Exception as exc:
            self._store.set_analysis_status(
                context.analysis_run_id,
                AnalysisStatus.FAILED,
                error=str(exc),
            )
            raise ExtensionExecutionError(manifest.id, str(exc)) from exc

        self._store.set_analysis_status(
            context.analysis_run_id,
            AnalysisStatus.COMPLETED,
        )
        return result
