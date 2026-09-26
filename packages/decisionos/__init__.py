"""DecisionOS — a probabilistic decision runtime for AI-native software.

DecisionOS combines probabilistic intelligence with deterministic policy
enforcement and outcome-based calibration.

The AI provider never directly executes actions: a provider produces a
probability distribution, the policy engine determines what is permitted,
and observed outcomes feed calibration.
"""

from __future__ import annotations

from decisionos.sdk import AsyncDecisionOS, DecisionOS
from decisionos.sdk.errors import (
    DecisionOSAPIError,
    DecisionOSConnectionError,
    DecisionOSError,
)

__version__ = "0.1.0"

__all__ = [
    "AsyncDecisionOS",
    "DecisionOS",
    "DecisionOSAPIError",
    "DecisionOSConnectionError",
    "DecisionOSError",
    "__version__",
]
