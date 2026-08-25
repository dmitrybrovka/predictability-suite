from importlib.util import find_spec

import pytest

from predictability.core.errors import ExtraMissingError
from predictability.models.quantile_catboost import QuantileCatBoostBackend, _require_catboost
from predictability.models.quantile_lightgbm import QuantileLightGBMBackend, _require_lgb


def test_registry_names_are_distinct() -> None:
    assert QuantileCatBoostBackend.name == "quantile_catboost"
    assert QuantileLightGBMBackend.name == "quantile_lightgbm"
    assert QuantileCatBoostBackend.name != QuantileLightGBMBackend.name


def test_catboost_extra_is_reported_or_usable() -> None:
    if find_spec("catboost") is None:
        with pytest.raises(ExtraMissingError, match=r"predictability\[catboost\]"):
            _require_catboost()
        return
    assert _require_catboost().__name__ == "CatBoostRegressor"


def test_lightgbm_extra_is_reported_or_usable() -> None:
    try:
        # An installed-but-unloadable wheel (no libomp) must also read as a
        # missing extra rather than an OSError escaping to the caller.
        import lightgbm
    except (ImportError, OSError):
        with pytest.raises(ExtraMissingError, match=r"predictability\[gbm\]"):
            _require_lgb()
        return
    assert _require_lgb().LGBMRegressor is lightgbm.LGBMRegressor
