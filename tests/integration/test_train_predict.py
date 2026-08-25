import logging
from pathlib import Path

import pytest

from predictability.core.config import AppConfig
from predictability.core.errors import UsageError
from predictability.core.synthetic import open_epic, two_team_history
from predictability.store.sqlite import Store
from predictability.training.trainer import predict, train


def _cfg() -> AppConfig:
    return AppConfig({"model": {"min_history": 5, "shrinkage_k": 2}, "factors": []})


def _factor_cfg(*names: str) -> AppConfig:
    return AppConfig(
        {
            "model": {"min_history": 5, "shrinkage_k": 2},
            "factors": [{"name": n, "enabled": True} for n in names],
        }
    )


def test_two_team_bias_and_open_excluded(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    history = two_team_history(n_per_team=20, late_slip=12, ontime_slip=0)
    open_late = open_epic("late-team", external_id="OPEN-L")
    open_on = open_epic("ontime-team", external_id="OPEN-O")
    store.upsert_epics([*history, open_late, open_on])
    cfg = _cfg()
    art = train("empirical_bayes", db, config=cfg)
    assert art.train_epic_count == 40
    results = predict(db, epics=[open_late, open_on], config=cfg)
    by_team = {r.team_id: r for r in results}
    late = by_team["late-team"]
    ontime = by_team["ontime-team"]
    assert late.on_time_probability < ontime.on_time_probability
    assert late.expected_slip > ontime.expected_slip
    assert "0.5" in late.quantiles
    assert "0.9" in late.quantiles
    assert late.model_id == str(art.id)
    assert late.cold_start is False
    assert late.team_history_n == 20
    assert late.factor_set_hash == art.factor_set_hash


def test_quantile_backend_separates_teams_at_predict_time(tmp_path: Path) -> None:
    """Gradient-boosted backends read the factor matrix, so predict must fit factors
    on the training history rather than on the open epics being scored."""
    pytest.importorskip("catboost")
    db = tmp_path / "db.sqlite"
    store = Store(db)
    store.upsert_epics(two_team_history(n_per_team=25, late_slip=12, ontime_slip=0))
    cfg = _factor_cfg("team_bias")
    train("quantile_catboost", db, config=cfg)
    late, ontime = predict(
        db,
        epics=[open_epic("late-team", external_id="L"), open_epic("ontime-team", external_id="O")],
        config=cfg,
    )
    assert late.expected_slip > ontime.expected_slip + 1
    assert late.on_time_probability < ontime.on_time_probability
    assert late.team_history_n == 25
    assert late.cold_start is False


def test_predict_scores_in_the_artifacts_slip_unit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    store.upsert_epics(two_team_history(n_per_team=10, late_slip=12, ontime_slip=0))
    working = AppConfig({"model": {"min_history": 5}, "factors": [{"name": "team_bias"}]})
    art = train("empirical_bayes", db, config=working)
    assert art.slip_unit == "working_days"

    calendar = AppConfig(
        {
            "model": {"min_history": 5},
            "slip": {"unit": "calendar_days"},
            "factors": [{"name": "team_bias"}],
        }
    )
    open_e = open_epic("late-team", external_id="OPEN-L")
    with caplog.at_level(logging.WARNING):
        rows = predict(db, epics=[open_e], config=calendar)
    assert rows[0].expected_slip == predict(db, epics=[open_e], config=working)[0].expected_slip
    assert "slip unit" in caplog.text


def test_cold_start_threshold_is_pinned_to_the_artifact(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    store.upsert_epics(two_team_history(n_per_team=10))
    art = train("empirical_bayes", db, config=_cfg())
    assert art.min_history == 5

    open_e = open_epic("late-team", external_id="OPEN-L")
    assert predict(db, epics=[open_e], config=_cfg())[0].cold_start is False
    raised = AppConfig({"model": {"min_history": 50, "shrinkage_k": 2}, "factors": []})
    with caplog.at_level(logging.WARNING):
        row = predict(db, epics=[open_e], config=raised)[0]
    # 10 completions still clear the threshold the artifact was trained under.
    assert row.cold_start is False
    assert row.team_history_n == 10
    assert "min_history" in caplog.text
    assert train("empirical_bayes", db, config=raised).min_history == 50
    assert predict(db, epics=[open_e], config=raised)[0].cold_start is True


def test_artifact_without_a_cutoff_uses_all_history(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    store.upsert_epics(two_team_history(n_per_team=10))
    trained = train("empirical_bayes", db, config=_cfg())
    uncut = store.save_artifact(
        backend=trained.backend,
        backend_version=trained.backend_version,
        factor_set_hash=trained.factor_set_hash,
        quantiles=trained.quantiles,
        slip_unit=trained.slip_unit,
        train_epic_count=trained.train_epic_count,
        train_team_count=trained.train_team_count,
        data_cutoff=None,
        blob_path=trained.blob_path,
        activate=False,
        min_history=trained.min_history,
    )
    row = predict(
        db,
        epics=[open_epic("late-team", external_id="OPEN-L")],
        model_id=str(uncut.id),
        config=_cfg(),
    )[0]
    assert row.team_history_n == 10
    assert row.model_id == str(uncut.id)


def test_predict_rejects_changed_factor_set(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    store.upsert_epics(two_team_history(n_per_team=10))
    art = train("empirical_bayes", db, config=_factor_cfg("team_bias"))
    open_e = open_epic("late-team", external_id="OPEN-L")
    with pytest.raises(UsageError, match="factor set changed"):
        predict(db, epics=[open_e], config=_factor_cfg("team_bias", "cross_team_deps"))
    rows = predict(db, epics=[open_e], config=_factor_cfg("team_bias"))
    assert rows[0].factor_set_hash == art.factor_set_hash
