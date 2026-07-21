from __future__ import annotations

from ..manifest import ExtensionManifest
from ..registry import ExtensionRegistry
from .session_statistics import (
    SESSION_STATISTICS_ALGORITHM_VERSION,
    SESSION_STATISTICS_ARTIFACT_SCHEMA_VERSION,
    SESSION_STATISTICS_PROVIDER_ID,
    SESSION_STATISTICS_PROVIDER_VERSION,
    SessionStatisticsProvider,
)


def builtin_analysis_providers() -> tuple[SessionStatisticsProvider, ...]:
    """Return trusted built-in providers without performing global registration."""

    return (SessionStatisticsProvider(),)


def register_builtin_extensions(
    registry: ExtensionRegistry,
) -> tuple[ExtensionManifest, ...]:
    """Explicitly register CRT-owned providers in the supplied registry."""

    return tuple(registry.register(provider) for provider in builtin_analysis_providers())


__all__ = [
    "SESSION_STATISTICS_ALGORITHM_VERSION",
    "SESSION_STATISTICS_ARTIFACT_SCHEMA_VERSION",
    "SESSION_STATISTICS_PROVIDER_ID",
    "SESSION_STATISTICS_PROVIDER_VERSION",
    "SessionStatisticsProvider",
    "builtin_analysis_providers",
    "register_builtin_extensions",
]
