from pathlib import Path

import numpy as np

from predictability.models.empirical_bayes import EmpiricalBayesBackend, identity_frame


def test_model_backend_protocol_methods(tmp_path: Path) -> None:
    backend: EmpiricalBayesBackend = EmpiricalBayesBackend(min_history=1)
    x = identity_frame(["t"] * 12)
    slip = np.linspace(-2, 8, 12)
    fitted = backend.fit(x, slip, {"min_history": 1})
    q = fitted.predict_quantiles(x, [0.5, 0.9])
    p = fitted.predict_on_time_proba(x)
    assert q.shape[0] == 12
    assert p.shape == (12,)
    dest = tmp_path / "art"
    dest.mkdir()
    fitted.save(dest)
    loaded = EmpiricalBayesBackend.load(dest)
    assert loaded.name == "empirical_bayes"
    np.testing.assert_allclose(loaded.predict_quantiles(x), q)
