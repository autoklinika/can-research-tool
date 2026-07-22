from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .contracts import AnalysisContext
from .manifest import (
    CRT_EXTENSION_API_VERSION,
    ExtensionManifest,
    ExtensionPermission,
    ExtensionType,
)


class ExtensionRegistrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExtensionLoadError:
    extension_id: str
    error: str


@runtime_checkable
class AnalysisProvider(Protocol):
    manifest: ExtensionManifest

    def run(self, context: AnalysisContext) -> object:
        ...


@runtime_checkable
class ComparisonProvider(Protocol):
    manifest: ExtensionManifest

    def run(self, context: AnalysisContext) -> object:
        ...


class ExtensionRegistry:
    """Explicit registry for trusted in-process CRT extensions.

    Stage 2 intentionally does not scan folders, import arbitrary project code or
    install dependencies. Every provider must be supplied explicitly by CRT code.
    """

    def __init__(
        self,
        *,
        crt_api_version: str = CRT_EXTENSION_API_VERSION,
        passive_only: bool = True,
        ai_enabled: bool = False,
    ) -> None:
        self.crt_api_version = crt_api_version
        self.passive_only = passive_only
        self.ai_enabled = ai_enabled
        self._providers: dict[str, object] = {}
        self._errors: list[ExtensionLoadError] = []

    @property
    def load_errors(self) -> tuple[ExtensionLoadError, ...]:
        return tuple(self._errors)

    def register(self, provider: object) -> ExtensionManifest:
        manifest = getattr(provider, "manifest", None)
        if not isinstance(manifest, ExtensionManifest):
            raise ExtensionRegistrationError(
                "extension provider must expose an ExtensionManifest as manifest"
            )
        self._validate_manifest_policy(manifest)
        if manifest.id in self._providers:
            raise ExtensionRegistrationError(f"duplicate extension id: {manifest.id}")
        if manifest.type == ExtensionType.ANALYSIS and not isinstance(provider, AnalysisProvider):
            raise ExtensionRegistrationError(
                f"analysis provider {manifest.id} does not implement run(context)"
            )
        if manifest.type == ExtensionType.COMPARISON and not isinstance(
            provider, ComparisonProvider
        ):
            raise ExtensionRegistrationError(
                f"comparison provider {manifest.id} does not implement run(context)"
            )
        self._providers[manifest.id] = provider
        return manifest

    def try_register(self, provider: object) -> bool:
        manifest = getattr(provider, "manifest", None)
        extension_id = manifest.id if isinstance(manifest, ExtensionManifest) else "<unknown>"
        try:
            self.register(provider)
            return True
        except Exception as exc:
            self._errors.append(ExtensionLoadError(extension_id, str(exc)))
            return False

    def get(self, extension_id: str) -> object:
        try:
            return self._providers[extension_id]
        except KeyError as exc:
            raise KeyError(f"unknown extension: {extension_id}") from exc

    def get_analysis(self, extension_id: str) -> AnalysisProvider:
        provider = self.get(extension_id)
        manifest = getattr(provider, "manifest")
        if manifest.type != ExtensionType.ANALYSIS:
            raise TypeError(f"extension is not an analysis provider: {extension_id}")
        if not isinstance(provider, AnalysisProvider):
            raise TypeError(f"analysis provider contract is invalid: {extension_id}")
        return provider

    def get_comparison(self, extension_id: str) -> ComparisonProvider:
        provider = self.get(extension_id)
        manifest = getattr(provider, "manifest")
        if manifest.type != ExtensionType.COMPARISON:
            raise TypeError(f"extension is not a comparison provider: {extension_id}")
        if not isinstance(provider, ComparisonProvider):
            raise TypeError(f"comparison provider contract is invalid: {extension_id}")
        return provider

    def manifests(
        self,
        *,
        extension_type: ExtensionType | str | None = None,
        input_kind: str | None = None,
    ) -> tuple[ExtensionManifest, ...]:
        selected_type = None if extension_type is None else ExtensionType(extension_type)
        manifests = []
        for provider in self._providers.values():
            manifest = getattr(provider, "manifest")
            if selected_type is not None and manifest.type != selected_type:
                continue
            if input_kind is not None and input_kind not in manifest.inputs:
                continue
            manifests.append(manifest)
        return tuple(sorted(manifests, key=lambda item: (item.type.value, item.name, item.id)))

    def _validate_manifest_policy(self, manifest: ExtensionManifest) -> None:
        if manifest.crt_api != self.crt_api_version:
            raise ExtensionRegistrationError(
                f"incompatible CRT extension API for {manifest.id}: "
                f"{manifest.crt_api} != {self.crt_api_version}"
            )
        if self.passive_only and (
            manifest.requires_can_tx or ExtensionPermission.CAN_TX in manifest.permissions
        ):
            raise ExtensionRegistrationError(
                f"passive CRT runtime rejects CAN TX extension: {manifest.id}"
            )
        if manifest.requires_ai and not self.ai_enabled:
            raise ExtensionRegistrationError(
                f"AI extension is disabled in this runtime: {manifest.id}"
            )

        allowed = {
            ExtensionPermission.PROJECT_READ,
            ExtensionPermission.SESSION_READ,
            ExtensionPermission.ARTIFACT_WRITE,
            ExtensionPermission.FINDING_WRITE,
        }
        if self.ai_enabled:
            allowed.add(ExtensionPermission.AI_USE)
        if not self.passive_only:
            allowed.add(ExtensionPermission.CAN_TX)
        unsupported = set(manifest.permissions) - allowed
        if unsupported:
            values = sorted(permission.value for permission in unsupported)
            raise ExtensionRegistrationError(
                f"extension requests unsupported permissions {values}: {manifest.id}"
            )
