"""Quantile LightGBM backend (optional extra)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from predictability.core.errors import ExtraMissingError, UsageError
from predictability.models.base import FeatureFrame


def _require_lgb() -> Any:
    try:
        import lightgbm as lgb
    except (ImportError, OSError) as exc:
        raise ExtraMissingError(
            "LightGBM is not installed. pip install predictability[gbm]"
        ) from exc
    return lgb


class QuantileLightGBMBackend:
    """Quantile LightGBM backend. Requires the ``[gbm]`` extra."""

    name = "quantile_lightgbm"
    version = "1.0.0"
    quantiles: Sequence[float] = (0.5, 0.9)

    def __init__(self) -> None:
        """Create an unfitted backend."""
        self._models: dict[str, Any] = {}
        self._columns: list[str] = []
        self._fitted = False

    def _prepare(self, x: FeatureFrame) -> pd.DataFrame:
        frame = x.copy()
        if "team_id" in frame.columns:
            frame["team_id"] = frame["team_id"].astype("category")
        return frame

    def fit(
        self, x: FeatureFrame, slip: NDArray[Any], meta: Mapping[str, Any]
    ) -> QuantileLightGBMBackend:
        """Fit one LightGBM quantile model per requested quantile.

        Raises:
            ExtraMissingError: ``predictability[gbm]`` is not installed.
        """
        lgb = _require_lgb()
        qs = tuple(float(q) for q in (meta.get("quantiles") or self.quantiles))
        self.quantiles = qs
        frame = self._prepare(x)
        self._columns = list(frame.columns)
        y = np.asarray(slip, dtype=float)
        for q in qs:
            model = lgb.LGBMRegressor(
                objective="quantile",
                alpha=q,
                n_estimators=80,
                verbosity=-1,
            )
            model.fit(frame, y)
            self._models[str(q)] = model
        self._fitted = True
        return self

    def predict_quantiles(
        self, x: FeatureFrame, quantiles: Sequence[float] | None = None
    ) -> NDArray[Any]:
        """Return slip quantiles with shape ``(n_epics, n_quantiles)``.

        Raises:
            UsageError: Called before ``fit``.
        """
        if not self._fitted:
            raise UsageError("quantile_lightgbm is not fitted")
        qs = list(quantiles if quantiles is not None else self.quantiles)
        frame = self._prepare(x)[self._columns]
        cols = [np.asarray(self._models[str(q)].predict(frame), dtype=float) for q in qs]
        return np.column_stack(cols)

    def predict_on_time_proba(self, x: FeatureFrame) -> NDArray[Any]:
        """Approximate P(slip <= 0) as a logistic of p50, not a Gaussian CDF."""
        q50 = self.predict_quantiles(x, [0.5])[:, 0]
        return 1.0 / (1.0 + np.exp(q50 / 5.0))

    def save(self, path: Path) -> None:
        """Pickle booster dicts and write ``meta.json`` into ``path``."""
        import pickle

        path.mkdir(parents=True, exist_ok=True)
        meta = {"columns": self._columns, "quantiles": list(self.quantiles), "fitted": self._fitted}
        (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (path / "models.pkl").write_bytes(pickle.dumps(self._models))

    @classmethod
    def load(cls, path: Path) -> QuantileLightGBMBackend:
        """Restore from ``path``.

        Raises:
            ExtraMissingError: ``predictability[gbm]`` is not installed.
        """
        import pickle

        _require_lgb()
        obj = cls()
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        obj._columns = meta["columns"]
        obj.quantiles = tuple(meta["quantiles"])
        obj._fitted = meta["fitted"]
        obj._models = pickle.loads((path / "models.pkl").read_bytes())
        return obj
