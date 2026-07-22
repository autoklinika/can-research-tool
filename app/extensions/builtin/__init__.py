from __future__ import annotations

from ..manifest import ExtensionManifest
from ..registry import ExtensionRegistry
from .comparison_statistics import (
    COMPARISON_STATISTICS_ALGORITHM_VERSION,
    COMPARISON_STATISTICS_ARTIFACT_SCHEMA_VERSION,
    COMPARISON_STATISTICS_PROVIDER_ID,
    COMPARISON_STATISTICS_PROVIDER_VERSION,
    ComparisonStatisticsProvider,
)
from .session_statistics import (
    SESSION_STATISTICS_ALGORITHM_VERSION,
    SESSION_STATISTICS_ARTIFACT_SCHEMA_VERSION,
    SESSION_STATISTICS_PROVIDER_ID,
    SESSION_STATISTICS_PROVIDER_VERSION,
    SessionStatisticsProvider,
)


def builtin_analysis_providers() -> tuple[SessionStatisticsProvider, ...]:
    """Return trusted single-session providers without global discovery."""

    return (SessionStatisticsProvider(),)


def builtin_comparison_providers() -> tuple[ComparisonStatisticsProvider, ...]:
    """Return trusted comparison providers without global discovery."""

    return (ComparisonStatisticsProvider(),)


def register_builtin_extensions(
    registry: ExtensionRegistry,
) -> tuple[ExtensionManifest, ...]:
    """Register the established single-session built-ins."""

    return tuple(registry.register(provider) for provider in builtin_analysis_providers())


def register_builtin_comparison_extensions(
    registry: ExtensionRegistry,
) -> tuple[ExtensionManifest, ...]:
    """Register CRT-owned passive comparison providers."""

    return tuple(registry.register(provider) for provider in builtin_comparison_providers())


__all__ = [
    "COMPARISON_STATISTICS_ALGORITHM_VERSION",
    "COMPARISON_STATISTICS_ARTIFACT_SCHEMA_VERSION",
    "COMPARISON_STATISTICS_PROVIDER_ID",
    "COMPARISON_STATISTICS_PROVIDER_VERSION",
    "ComparisonStatisticsProvider",
    "SESSION_STATISTICS_ALGORITHM_VERSION",
    "SESSION_STATISTICS_ARTIFACT_SCHEMA_VERSION",
    "SESSION_STATISTICS_PROVIDER_ID",
    "SESSION_STATISTICS_PROVIDER_VERSION",
    "SessionStatisticsProvider",
    "builtin_analysis_providers",
    "builtin_comparison_providers",
    "register_builtin_comparison_extensions",
    "register_builtin_extensions",
]
