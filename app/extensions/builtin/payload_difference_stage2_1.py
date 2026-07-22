from __future__ import annotations

from app.domain import Artifact

from ..contracts import AnalysisContext
from ..manifest import ExtensionManifest
from . import payload_difference as _stage2
from . import payload_difference_exact as _exact


PAYLOAD_DIFFERENCE_PROVIDER_ID = _exact.PAYLOAD_DIFFERENCE_PROVIDER_ID
PAYLOAD_DIFFERENCE_PROVIDER_VERSION = "1.0.0"
PAYLOAD_DIFFERENCE_ALGORITHM_VERSION = _exact.PAYLOAD_DIFFERENCE_ALGORITHM_VERSION
PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION = (
    _exact.PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION
)


class PayloadDifferenceProvider(_exact.PayloadDifferenceProvider):
    """Stage 2.1 provider with exact defaults and legacy parameter support."""

    manifest = ExtensionManifest(
        id=PAYLOAD_DIFFERENCE_PROVIDER_ID,
        name=_exact.PayloadDifferenceProvider.manifest.name,
        version=PAYLOAD_DIFFERENCE_PROVIDER_VERSION,
        crt_api=_exact.PayloadDifferenceProvider.manifest.crt_api,
        type=_exact.PayloadDifferenceProvider.manifest.type,
        inputs=_exact.PayloadDifferenceProvider.manifest.inputs,
        outputs=_exact.PayloadDifferenceProvider.manifest.outputs,
        permissions=_exact.PayloadDifferenceProvider.manifest.permissions,
    )
    algorithm_version = PAYLOAD_DIFFERENCE_ALGORITHM_VERSION

    def run(self, context: AnalysisContext) -> Artifact:
        parameters = dict(context.inputs[0].parameters)
        if "max_variants_per_message" in parameters:
            return _stage2.PayloadDifferenceProvider().run(context)
        return super().run(context)


__all__ = [
    "PAYLOAD_DIFFERENCE_ALGORITHM_VERSION",
    "PAYLOAD_DIFFERENCE_ARTIFACT_SCHEMA_VERSION",
    "PAYLOAD_DIFFERENCE_PROVIDER_ID",
    "PAYLOAD_DIFFERENCE_PROVIDER_VERSION",
    "PayloadDifferenceProvider",
]
