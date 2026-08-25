from pathlib import Path

from predictability.core.config import AppConfig
from predictability.core.synthetic import two_team_history
from predictability.store.sqlite import Store
from predictability.training.trainer import train


def test_train_activates_new_artifact(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    store.upsert_epics(two_team_history(n_per_team=10))
    cfg = AppConfig({"model": {"min_history": 3}, "factors": []})
    a1 = train("empirical_bayes", db, config=cfg)
    a2 = train("empirical_bayes", db, config=cfg)
    assert a1.id != a2.id
    assert store.get_artifact().id == a2.id
    assert store.get_artifact(a1.id).is_active is False
    assert a2.is_active is True
