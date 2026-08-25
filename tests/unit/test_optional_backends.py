from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from predictability.core.errors import ExtraMissingError, UsageError
from predictability.models.quantile_catboost import QuantileCatBoostBackend
from predictability.models.quantile_lightgbm import QuantileLightGBMBackend, _require_lgb


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"team_id": ["a", "a", "b", "b"], "team_n": [1.0, 2.0, 1.0, 3.0]})


def _slip() -> np.ndarray:
    return np.array([2.0, 3.0, 0.0, 0.5], dtype=float)


def test_catboost_fit_save_load_predict(tmp_path: Path) -> None:
    pytest.importorskip("catboost")
    model = QuantileCatBoostBackend()
    x = _frame()
    model.fit(x, _slip(), {"quantiles": (0.5, 0.9)})
    q = model.predict_quantiles(x)
    p = model.predict_on_time_proba(x)
    assert q.shape == (4, 2)
    assert p.shape == (4,)
    blob = tmp_path / "cb"
    model.save(blob)
    loaded = QuantileCatBoostBackend.load(blob)
    assert loaded.predict_quantiles(x).shape == (4, 2)


def test_catboost_unfitted_predict_raises() -> None:
    pytest.importorskip("catboost")
    with pytest.raises(UsageError):
        QuantileCatBoostBackend().predict_quantiles(_frame())


def test_lightgbm_fit_save_load_predict(tmp_path: Path) -> None:
    try:
        _require_lgb()
    except ExtraMissingError:
        pytest.skip("lightgbm extra is not usable")
    model = QuantileLightGBMBackend()
    x = _frame()
    model.fit(x, _slip(), {"quantiles": (0.5, 0.9)})
    q = model.predict_quantiles(x)
    p = model.predict_on_time_proba(x)
    assert q.shape == (4, 2)
    assert len(p) == 4
    blob = tmp_path / "lgb"
    model.save(blob)
    loaded = QuantileLightGBMBackend.load(blob)
    assert loaded.predict_quantiles(x).shape == (4, 2)


def test_lightgbm_unfitted_predict_raises() -> None:
    with pytest.raises(UsageError):
        QuantileLightGBMBackend().predict_quantiles(_frame())
