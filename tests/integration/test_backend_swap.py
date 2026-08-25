from pathlib import Path

import pytest

from predictability.core.config import AppConfig
from predictability.core.errors import ExtraMissingError
from predictability.core.synthetic import two_team_history
from predictability.evaluation.backtest import evaluate
from predictability.store.sqlite import Store
from predictability.training.trainer import predict, train


def test_evaluate_then_train_swaps_backend(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    store.upsert_epics(two_team_history(n_per_team=25))
    cfg = AppConfig({"model": {"min_history": 5}, "factors": []})
    train("empirical_bayes", db, config=cfg)
    report = evaluate(db, ["empirical_bayes", "quantile_catboost"], config=cfg, min_train=10)
    assert report.rows[0].backend == "empirical_bayes"
    active = store.active_id()
    try:
        art = train("quantile_catboost", db, config=cfg)
    except ExtraMissingError:
        pytest.skip("catboost extra not installed")
    assert store.active_id() != active
    from predictability.core.synthetic import open_epic

    r = predict(db, epics=[open_epic("late-team")], config=cfg)[0]
    assert r.backend == "quantile_catboost"
    assert r.model_id == str(art.id)
    # evaluate must not have been the thing that swapped
    assert any(row.backend == "quantile_catboost" for row in report.rows)
