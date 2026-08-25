from pathlib import Path

from predictability.core.config import AppConfig
from predictability.evaluation.backtest import evaluate
from predictability.store.sqlite import Store
from predictability.training.trainer import train
from tests.fixtures.walkforward import large_history


def test_walkforward_does_not_mutate_active(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    store.upsert_epics(large_history(n=120))
    cfg = AppConfig({"model": {"min_history": 5}, "factors": []})
    art = train("empirical_bayes", db, config=cfg)
    report = evaluate(db, ["empirical_bayes"], config=cfg, min_train=20, horizon_epics=15)
    assert store.get_artifact().id == art.id
    assert store.get_artifact().is_active is True
    row = report.rows[0]
    assert row.artifact_id is None
    assert row.n_eval > 0
    assert row.mae_slip is not None
    assert "0.9" in row.pinball
    assert row.brier_on_time is not None
