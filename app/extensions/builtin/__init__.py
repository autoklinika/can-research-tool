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
from .message_sequence_exact import (
    MESSAGE_SEQUENCE_ALGORITHM_VERSION,
    MESSAGE_SEQUENCE_ARTIFACT_SCHEMA_VERSION,
    MESSAGE_SEQUENCE_PROVIDER_ID,
    MESSAGE_SEQUENCE_PROVIDER_VERSION,
    MessageSequenceComparisonProvider,
)
from .payload_difference_exact import (
    PAYLOAD_DIFFERENCE_ALGORITHM_VERSION,
    PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION,
    PAYLOAD_DIFFERENCE_PROVIDER_ID,
    PAYLOAD_DIFFERENCE_PROVIDER_VERSION,
    PayloadDifferenceProvider,
)
from .session_statistics import (
    SESSION_STATISTICS_ALGORITHM_VERSION,
    SESSION_STATISTICS_ARTIFACT_SCHEMA_VERSION,
    SESSION_STATISTICS_PROVIDER_ID,
    SESSION_STATISTICS_PROVIDER_VERSION,
    SessionStatisticsProvider,
)
from .signal_discovery import (
    SIGNAL_DISCOVERY_ALGORITHM_VERSION,
    SIGNAL_DISCOVERY_ARTIFACT_SCHEMA_VERSION,
    SIGNAL_DISCOVERY_PROVIDER_ID,
    SIGNAL_DISCOVERY_PROVIDER_VERSION,
    SignalDiscoveryActivityProvider,
)


def builtin_analysis_providers() -> tuple[
    SessionStatisticsProvider | SignalDiscoveryActivityProvider,
    ...,
]:
    """Return trusted single-session providers without global discovery."""

    return (
        SessionStatisticsProvider(),
        SignalDiscoveryActivityProvider(),
    )


def builtin_comparison_providers() -> tuple[
    ComparisonStatisticsProvider
    | PayloadDifferenceProvider
    | MessageSequenceComparisonProvider,
    ...,
]:
    """Return CRT-owned passive comparison providers."""

    return (
        ComparisonStatisticsProvider(),
        PayloadDifferenceProvider(),
        MessageSequenceComparisonProvider(),
    )


def register_builtin_extensions(
    registry: ExtensionRegistry,
) -> tuple[ExtensionManifest, ...]:
    """Register the established single-session built-ins."""

    return tuple(
        registry.register(provider)
        for provider in builtin_analysis_providers()
    )


def register_builtin_comparison_extensions(
    registry: ExtensionRegistry,
) -> tuple[ExtensionManifest, ...]:
    """Register CRT-owned passive comparison providers."""

    return tuple(
        registry.register(provider)
        for provider in builtin_comparison_providers()
    )


__all__ = [
    "COMPARISON_STATISTICS_ALGORITHM_VERSION",
    "COMPARISON_STATISTICS_ARTIFACT_SCHEMA_VERSION",
    "COMPARISON_STATISTICS_PROVIDER_ID",
    "COMPARISON_STATISTICS_PROVIDER_VERSION",
    "ComparisonStatisticsProvider",
    "MESSAGE_SEQUENCE_ALGORITHM_VERSION",
    "MESSAGE_SEQUENCE_ARTIFACT_SCHEMA_VERSION",
    "MESSAGE_SEQUENCE_PROVIDER_ID",
    "MESSAGE_SEQUENCE_PROVIDER_VERSION",
    "MessageSequenceComparisonProvider",
    "PAYLOAD_DIFFERENCE_ALGORITHM_VERSION",
    "PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION",
    "PAYLOAD_DIFFERENCE_PROVIDER_ID",
    "PAYLOAD_DIFFERENCE_PROVIDER_VERSION",
    "PayloadDifferenceProvider",
    "SESSION_STATISTICS_ALGORITHM_VERSION",
    "SESSION_STATISTICS_ARTIFACT_SCHEMA_VERSION",
    "SESSION_STATISTICS_PROVIDER_ID",
    "SESSION_STATISTICS_PROVIDER_VERSION",
    "SessionStatisticsProvider",
    "SIGNAL_DISCOVERY_ALGORITHM_VERSION",
    "SIGNAL_DISCOVERY_ARTIFACT_SCHEMA_VERSION",
    "SIGNAL_DISCOVERY_PROVIDER_ID",
    "SIGNAL_DISCOVERY_PROVIDER_VERSION",
    "SignalDiscoveryActivityProvider",
    "builtin_analysis_providers",
    "builtin_comparison_providers",
    "register_builtin_comparison_extensions",
    "register_builtin_extensions",
]
