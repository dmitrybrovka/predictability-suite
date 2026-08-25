from pathlib import Path

import numpy as np

from predictability.models.empirical_bayes import EmpiricalBayesBackend, identity_frame


def test_shrinkage_formula() -> None:
    x = identity_frame(["a", "a", "a", "b", "b"], ["1", "2", "3", "4", "5"])
    slip = np.array([10.0, 10.0, 10.0, 0.0, 0.0])
    model = EmpiricalBayesBackend(shrinkage_k=10, min_history=1)
    model.fit(x, slip, {"min_history": 1, "shrinkage_k": 10})
    # team a: n=3, w=3/13, mu = w*10 + (1-w)*6
    w = 3 / 13
    global_mean = float(np.mean(slip))
    expected = w * 10 + (1 - w) * global_mean
    assert model.team_stats["a"]["mu"] == expected
    assert model.team_stats["a"]["w"] == w


def test_min_history_uses_global_prior() -> None:
    x = identity_frame(["a"] * 5 + ["b"] * 2)
    slip = np.array([10.0] * 5 + [0.0] * 2)
    model = EmpiricalBayesBackend(min_history=5, shrinkage_k=10)
    model.fit(x, slip, {"min_history": 5})
    q = model.predict_quantiles(identity_frame(["a", "b", "never-seen"]), [0.5])
    # b has fewer than min_history completions, so it predicts the same global
    # prior as a team absent from training; a keeps its own higher estimate.
    assert q[1, 0] == q[2, 0]
    assert q[0, 0] > q[1, 0]


def test_quantiles_and_save_load(tmp_path: Path) -> None:
    x = identity_frame(["a"] * 8)
    slip = np.array([2.0] * 8)
    model = EmpiricalBayesBackend(min_history=1)
    model.fit(x, slip, {"min_history": 1, "quantiles": [0.5, 0.9]})
    q = model.predict_quantiles(x)
    p = model.predict_on_time_proba(x)
    assert q.shape == (8, 2)
    assert q[0, 0] <= q[0, 1]
    assert 0.0 <= p[0] <= 1.0
    dest = tmp_path / "m"
    dest.mkdir()
    model.save(dest)
    loaded = EmpiricalBayesBackend.load(dest)
    q2 = loaded.predict_quantiles(x)
    np.testing.assert_allclose(q, q2)
