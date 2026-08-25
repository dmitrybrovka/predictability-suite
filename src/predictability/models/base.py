"""Model backend protocol."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
from numpy.typing import NDArray

FeatureFrame = pd.DataFrame


class ModelBackend(Protocol):
    name: str
    version: str
    quantiles: Sequence[float]

    def fit(self, x: FeatureFrame, slip: NDArray[Any], meta: Mapping[str, Any]) -> ModelBackend: ...

    def partial_fit(
        self, x: FeatureFrame, slip: NDArray[Any], meta: Mapping[str, Any]
    ) -> ModelBackend:
        """Optional. v1 trainer uses full refit if this is a no-op."""
        return self.fit(x, slip, meta)

    def predict_quantiles(
        self, x: FeatureFrame, quantiles: Sequence[float] | None = None
    ) -> NDArray[Any]: ...

    def predict_on_time_proba(self, x: FeatureFrame) -> NDArray[Any]: ...

    def save(self, path: Path) -> None: ...

    @classmethod
    def load(cls, path: Path) -> ModelBackend: ...
