from __future__ import annotations

# Import registers the Stage 2 operator-review article in the shared Help catalog.
from app.help_catalog_signal_hypothesis_review import (
    SIGNAL_HYPOTHESIS_REVIEW_HELP_TOPIC as _SIGNAL_HYPOTHESIS_REVIEW_HELP_TOPIC,
)

from .signal_hypothesis_view_stage2 import SignalHypothesisView


__all__ = ["SignalHypothesisView"]
