from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from predictability.core.config import AppConfig
from predictability.core.synthetic import two_team_history
from predictability.evaluation.backtest import evaluate
from predictability.models.base import FeatureFrame
from predictability.store.sqlite import Store
from predictability.training.trainer import train


class StubModel:
    name = "stub_model"
    version = "0"
    quantiles: Sequence[float] = (0.5, 0.9)

    def fit(self, x: FeatureFrame, slip: NDArray[Any], meta: Mapping[str, Any]) -> StubModel:
        self._mean = float(np.mean(slip))
        return self

    def predict_quantiles(
        self, x: FeatureFrame, quantiles: Sequence[float] | None = None
    ) -> NDArray[Any]:
        qs = list(quantiles or self.quantiles)
        return np.tile(np.array([self._mean, self._mean + 1.0]), (len(x), 1))[:, : len(qs)]

    def predict_on_time_proba(self, x: FeatureFrame) -> NDArray[Any]:
        return np.full(len(x), 0.5)

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "ok").write_text("1", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> StubModel:
        obj = cls()
        obj._mean = 0.0
        return obj


def test_custom_model_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import predictability.training.trainer as tr

    monkeypatch.setitem(tr._BACKENDS, "stub_model", StubModel)
    db = tmp_path / "db.sqlite"
    Store(db).upsert_epics(two_team_history(n_per_team=12))
    cfg = AppConfig({"model": {"min_history": 3}, "factors": []})
    art = train("stub_model", db, config=cfg)
    assert art.backend == "stub_model"
    report = evaluate(db, ["stub_model"], config=cfg, min_train=6)
    assert report.rows[0].backend == "stub_model"
    assert report.rows[0].error is None
