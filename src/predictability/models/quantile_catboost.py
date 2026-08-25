"""Quantile CatBoost backend (optional extra)."""

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


def _require_catboost() -> Any:
    try:
        from catboost import CatBoostRegressor
    except ImportError as exc:
        raise ExtraMissingError(
            "CatBoost is not installed. pip install predictability[catboost]"
        ) from exc
    return CatBoostRegressor


class QuantileCatBoostBackend:
    name = "quantile_catboost"
    version = "1.0.0"
    quantiles: Sequence[float] = (0.5, 0.9)

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}
        self._columns: list[str] = []
        self._fitted = False

    def _prepare(self, x: FeatureFrame) -> pd.DataFrame:
        frame = x.copy()
        if "team_id" in frame.columns:
            frame["team_id"] = frame["team_id"].astype(str)
        return frame

    def fit(
        self, x: FeatureFrame, slip: NDArray[Any], meta: Mapping[str, Any]
    ) -> QuantileCatBoostBackend:
        regressor_cls = _require_catboost()
        qs = tuple(float(q) for q in (meta.get("quantiles") or self.quantiles))
        self.quantiles = qs
        frame = self._prepare(x)
        self._columns = list(frame.columns)
        cat_features = [i for i, c in enumerate(self._columns) if c == "team_id"]
        y = np.asarray(slip, dtype=float)
        for q in qs:
            model = regressor_cls(
                loss_function=f"Quantile:alpha={q}",
                depth=4,
                iterations=80,
                verbose=False,
                allow_writing_files=False,
                allow_const_label=True,
            )
            model.fit(frame, y, cat_features=cat_features)
            self._models[str(q)] = model
        self._fitted = True
        return self

    def predict_quantiles(
        self, x: FeatureFrame, quantiles: Sequence[float] | None = None
    ) -> NDArray[Any]:
        if not self._fitted:
            raise UsageError("quantile_catboost is not fitted")
        qs = list(quantiles if quantiles is not None else self.quantiles)
        frame = self._prepare(x)[self._columns]
        cols = []
        for q in qs:
            pred = self._models[str(q)].predict(frame)
            cols.append(np.asarray(pred, dtype=float))
        return np.column_stack(cols)

    def predict_on_time_proba(self, x: FeatureFrame) -> NDArray[Any]:
        q50 = self.predict_quantiles(x, [0.5])[:, 0]
        # crude: logistic of negative expected slip
        return 1.0 / (1.0 + np.exp(q50 / 5.0))

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        meta = {"columns": self._columns, "quantiles": list(self.quantiles), "fitted": self._fitted}
        (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        for q, model in self._models.items():
            model.save_model(str(path / f"q{q}.cbm"))

    @classmethod
    def load(cls, path: Path) -> QuantileCatBoostBackend:
        regressor_cls = _require_catboost()
        obj = cls()
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        obj._columns = meta["columns"]
        obj.quantiles = tuple(meta["quantiles"])
        obj._fitted = meta["fitted"]
        for q in obj.quantiles:
            m = regressor_cls()
            m.load_model(str(path / f"q{q}.cbm"))
            obj._models[str(q)] = m
        return obj
