from pathlib import Path

import pytest

from predictability.core.config import AppConfig
from predictability.core.synthetic import make_epic, two_team_history
from predictability.store.sqlite import Store
from predictability.training.trainer import predict, train


def test_cold_start_then_history(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    cfg = AppConfig({"model": {"min_history": 8, "shrinkage_k": 2}, "factors": []})
    store.upsert_epics(two_team_history(n_per_team=12))
    store.upsert_epics(
        [make_epic(external_id="C-1", team_id="new-c", slip_days=3, open_item=False)]
    )
    train("empirical_bayes", db, config=cfg)
    open_c = make_epic(external_id="C-OPEN", team_id="new-c", slip_days=0, open_item=True)
    store.upsert_epics([open_c])
    r = predict(db, epics=[open_c], config=cfg)[0]
    assert r.cold_start is True
    more = [make_epic(external_id=f"C-h{i}", team_id="new-c", slip_days=3) for i in range(10)]
    store.upsert_epics(more)
    train("empirical_bayes", db, config=cfg)
    r2 = predict(db, epics=[open_c], config=cfg)[0]
    assert r2.cold_start is False
    assert r2.team_history_n == 11


@pytest.mark.parametrize("backend", ["empirical_bayes", "quantile_catboost"])
def test_cold_start_is_backend_independent(tmp_path: Path, backend: str) -> None:
    if backend == "quantile_catboost":
        pytest.importorskip("catboost")
    db = tmp_path / f"{backend}.sqlite"
    store = Store(db)
    cfg = AppConfig({"model": {"min_history": 8, "shrinkage_k": 2}, "factors": []})
    store.upsert_epics(two_team_history(n_per_team=12))
    store.upsert_epics([make_epic(external_id="C-1", team_id="new-c", slip_days=3)])
    train(backend, db, config=cfg)
    thin = make_epic(external_id="C-OPEN", team_id="new-c", slip_days=0, open_item=True)
    thick = make_epic(external_id="L-OPEN", team_id="late-team", slip_days=0, open_item=True)
    rows = {r.external_id: r for r in predict(db, epics=[thin, thick], config=cfg)}
    assert rows["C-OPEN"].cold_start is True
    assert rows["C-OPEN"].team_history_n == 1
    assert rows["L-OPEN"].cold_start is False
    assert rows["L-OPEN"].team_history_n == 12
