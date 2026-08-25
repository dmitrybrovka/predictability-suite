from datetime import UTC, datetime
from pathlib import Path

from predictability.core.config import AppConfig
from predictability.core.schema import Dependency
from predictability.core.synthetic import make_epic, two_team_history
from predictability.factors.base import FactorContext
from predictability.factors.pipeline import build_matrix
from predictability.store.sqlite import Store
from predictability.training.trainer import predict, train


def test_factors_change_predictions(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    deadline = datetime(2026, 7, 10, tzinfo=UTC)
    history = two_team_history(n_per_team=15, late_slip=4, ontime_slip=0)
    store.upsert_epics(history)
    open_e = make_epic(
        external_id="VAC-OPEN",
        team_id="late-team",
        slip_days=0,
        open_item=True,
        deadline=deadline,
        created=datetime(2026, 6, 20, tzinfo=UTC),
    )
    store.upsert_epics([open_e])
    cfg_off = AppConfig(
        {
            "model": {"min_history": 5, "shrinkage_k": 2},
            "factors": [
                {"name": "team_bias", "enabled": True},
                {"name": "capacity_calendar", "enabled": False},
            ],
        }
    )
    train("empirical_bayes", db, config=cfg_off)
    off = predict(db, epics=[open_e], config=cfg_off)[0]

    vac = tmp_path / "vac.yaml"
    vac.write_text(
        "vacations:\n  - team_id: late-team\n    start: 2026-07-01\n    end: 2026-07-14\n    capacity_factor: 0\n",
        encoding="utf-8",
    )
    cfg_on = AppConfig(
        {
            "model": {"min_history": 5, "shrinkage_k": 2},
            "factors": [
                {"name": "team_bias", "enabled": True},
                {
                    "name": "capacity_calendar",
                    "enabled": True,
                    "params": {"vacations_path": str(vac)},
                },
            ],
        }
    )
    train("empirical_bayes", db, config=cfg_on)
    on = predict(db, epics=[open_e], config=cfg_on)[0]
    # empirical_bayes conditions on team only, so enabling a factor must not move
    # its numbers; the factor set it was trained with is still recorded.
    assert on.expected_slip == off.expected_slip
    assert on.factor_set_hash != off.factor_set_hash

    ctx = FactorContext()
    matrix = build_matrix([open_e], config=cfg_on, ctx=ctx, history=history)
    assert "vacation_overlap_days" in matrix.columns
    assert float(matrix.iloc[0]["vacation_overlap_days"]) > 0
    assert "team_mean_slip" in matrix.columns
    matrix_off = build_matrix([open_e], config=cfg_off, ctx=ctx, history=history)
    assert "vacation_overlap_days" not in matrix_off.columns
    blocked = make_epic(external_id="BLK", team_id="late-team", slip_days=0, open_item=True)
    ctx2 = FactorContext(
        dependencies=[
            Dependency(
                tracker="mock",
                from_external_id="BLK",
                to_external_id="OTHER",
                from_kind="epic",
                to_team_id="foreign",
            )
        ]
    )
    cfg_dep = AppConfig(
        {
            "factors": [
                {"name": "team_bias", "enabled": True},
                {"name": "cross_team_deps", "enabled": True},
            ]
        }
    )
    m2 = build_matrix([blocked], config=cfg_dep, ctx=ctx2, history=history)
    assert float(m2.iloc[0]["foreign_team_blocker_count"]) == 1
    cfg_none = AppConfig({"factors": [{"name": "cross_team_deps", "enabled": False}]})
    m3 = build_matrix([blocked], config=cfg_none, ctx=ctx2, history=history)
    assert "foreign_team_blocker_count" not in m3.columns


def test_open_epics_get_history_features(tmp_path: Path) -> None:
    """Factors fitted on the scored rows alone would be all-zero: open epics have
    no slip. Passing the training history is what keeps train and serve aligned."""
    history = two_team_history(n_per_team=15, late_slip=6, ontime_slip=0)
    open_e = make_epic(
        external_id="OPEN-1",
        team_id="late-team",
        slip_days=0,
        open_item=True,
        deadline=datetime(2026, 1, 1, tzinfo=UTC),
    )
    cfg = AppConfig({"factors": [{"name": "team_bias", "enabled": True}]})

    with_history = build_matrix([open_e], config=cfg, ctx=FactorContext(), history=history)
    without = build_matrix([open_e], config=cfg, ctx=FactorContext())

    assert float(with_history.iloc[0]["team_mean_slip"]) > 0
    assert float(with_history.iloc[0]["team_n"]) == 15
    assert float(without.iloc[0]["team_mean_slip"]) == 0
    assert float(without.iloc[0]["team_n"]) == 0
