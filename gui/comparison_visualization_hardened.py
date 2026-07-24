from __future__ import annotations

from typing import Any

from app.artifact_catalog import ArtifactIntegrityError

from .comparison_visualization import (
    _ARTIFACT_TYPES,
    _SUPPORTED_SCHEMAS,
    ComparisonVisualizationDialog as _BaseComparisonVisualizationDialog,
)


class ComparisonVisualizationDialog(_BaseComparisonVisualizationDialog):
    """Comparison dialog that reports persisted-artifact read failures."""

    def _refresh_dashboard(self) -> None:
        if self.dashboard is None:
            return

        latest = {}
        for artifact in self._artifacts:
            if artifact.artifact_type not in _ARTIFACT_TYPES:
                continue
            current = latest.get(artifact.artifact_type)
            if current is None or artifact.created_at_utc > current.created_at_utc:
                latest[artifact.artifact_type] = artifact

        payloads: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for artifact in latest.values():
            try:
                payload = self.service.artifacts.read_json(artifact)
            except (ArtifactIntegrityError, OSError, ValueError) as exc:
                errors.append(f"{artifact.artifact_type}: {exc}")
                continue
            if not isinstance(payload, dict):
                errors.append(f"{artifact.artifact_type}: korzeń JSON nie jest obiektem")
                continue
            schema = str(payload.get("schema") or "")
            if schema not in _SUPPORTED_SCHEMAS:
                errors.append(
                    f"{artifact.artifact_type}: nieobsługiwany schemat {schema or 'brak'}"
                )
                continue
            payloads[schema] = payload

        if payloads:
            self.dashboard.set_payloads(payloads)
        else:
            self.dashboard.clear()

        if errors:
            self.status_label.setText(
                "Nie udało się odczytać części artefaktów porównania: "
                + "; ".join(errors)
            )


__all__ = ["ComparisonVisualizationDialog"]
