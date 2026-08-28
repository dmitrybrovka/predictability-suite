"""Model backend protocol."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
from numpy.typing import NDArray

FeatureFrame = pd.DataFrame


class ModelBackend(Protocol):
    """Swap learning libraries without changing adapters or factors."""

    name: str
    version: str
    quantiles: Sequence[float]

    def fit(self, x: FeatureFrame, slip: NDArray[Any], meta: Mapping[str, Any]) -> ModelBackend:
        """Fit on completed-epic features and slip labels."""
        ...

    def partial_fit(
        self, x: FeatureFrame, slip: NDArray[Any], meta: Mapping[str, Any]
    ) -> ModelBackend:
        """Optional incremental fit. v1 trainer uses full refit if this is a no-op."""
        return self.fit(x, slip, meta)

    def predict_quantiles(
        self, x: FeatureFrame, quantiles: Sequence[float] | None = None
    ) -> NDArray[Any]:
        """Return slip quantiles with shape ``(n_epics, n_quantiles)``."""
        ...

    def predict_on_time_proba(self, x: FeatureFrame) -> NDArray[Any]:
        """Return P(slip <= 0) per row.

        ``empirical_bayes`` uses a Gaussian CDF. Quantile GBM backends return a
        logistic of p50 as an approximation, not a calibrated probability.
        """
        ...

    def save(self, path: Path) -> None:
        """Serialize into ``path`` (file or directory)."""
        ...

    @classmethod
    def load(cls, path: Path) -> ModelBackend:
        """Restore a fitted backend from ``path``."""
        ...
