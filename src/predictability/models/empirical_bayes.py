"""Empirical Bayes team-slip shrinkage baseline."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from predictability.core.errors import EmptyTrainSetError, UsageError
from predictability.models.base import FeatureFrame

_EPS = 1e-6


class EmpiricalBayesBackend:
    """Team-slip shrinkage baseline. Prior is the global mean estimated from data."""

    name = "empirical_bayes"
    version = "1.0.0"
    quantiles: Sequence[float] = (0.5, 0.9)

    def __init__(self, *, shrinkage_k: float = 10.0, min_history: int = 20) -> None:
        """Set shrinkage ``k`` and the cold-start threshold ``min_history``."""
        self.shrinkage_k = shrinkage_k
        self.min_history = min_history
        self.global_mean = 0.0
        self.global_std = 1.0
        self.team_stats: dict[str, dict[str, float]] = {}
        self._fitted = False

    def fit(
        self, x: FeatureFrame, slip: NDArray[Any], meta: Mapping[str, Any]
    ) -> EmpiricalBayesBackend:
        """Estimate global and per-team Gaussian slip parameters.

        Raises:
            EmptyTrainSetError: ``slip`` is empty.
        """
        if len(slip) == 0:
            raise EmptyTrainSetError("no completed epics to train on")
        self.shrinkage_k = float(meta.get("shrinkage_k", self.shrinkage_k))
        self.min_history = int(meta.get("min_history", self.min_history))
        qs = meta.get("quantiles")
        if qs:
            self.quantiles = tuple(float(q) for q in qs)
        teams = x["team_id"].astype(str).to_numpy()
        self.global_mean = float(np.mean(slip))
        self.global_std = max(float(np.std(slip, ddof=1)) if len(slip) > 1 else 1.0, 0.5)
        self.team_stats = {}
        for team in np.unique(teams):
            mask = teams == team
            values = slip[mask]
            n = float(len(values))
            mean = float(np.mean(values))
            std = max(float(np.std(values, ddof=1)) if len(values) > 1 else self.global_std, 0.5)
            w = n / (n + self.shrinkage_k)
            self.team_stats[str(team)] = {
                "n": n,
                "mean": mean,
                "std": std,
                "w": w,
                "mu": w * mean + (1.0 - w) * self.global_mean,
            }
        self._fitted = True
        return self

    def _row_params(self, team_id: str) -> tuple[float, float, int, bool]:
        stats = self.team_stats.get(team_id)
        if stats is None or int(stats["n"]) < self.min_history:
            n = 0 if stats is None else int(stats["n"])
            return self.global_mean, self.global_std, n, True
        return stats["mu"], stats["std"], int(stats["n"]), False

    def predict_quantiles(
        self, x: FeatureFrame, quantiles: Sequence[float] | None = None
    ) -> NDArray[Any]:
        """Return Gaussian quantile slip. Teams below ``min_history`` use the global prior.

        Raises:
            UsageError: Called before ``fit``.
        """
        if not self._fitted:
            raise UsageError("empirical_bayes is not fitted")
        qs = list(quantiles if quantiles is not None else self.quantiles)
        out = np.zeros((len(x), len(qs)))
        for i, team in enumerate(x["team_id"].astype(str).tolist()):
            mu, sigma, _n, _cs = self._row_params(team)
            dist = NormalDist(mu, sigma)
            for j, q in enumerate(qs):
                out[i, j] = dist.inv_cdf(q)
        return out

    def predict_on_time_proba(self, x: FeatureFrame) -> NDArray[Any]:
        """Return P(slip <= 0) from the same Gaussian as the quantiles.

        Raises:
            UsageError: Called before ``fit``.
        """
        if not self._fitted:
            raise UsageError("empirical_bayes is not fitted")
        out = np.zeros(len(x))
        for i, team in enumerate(x["team_id"].astype(str).tolist()):
            mu, sigma, _n, _cs = self._row_params(team)
            out[i] = NormalDist(mu, sigma).cdf(0.0)
        return out

    def save(self, path: Path) -> None:
        """Write ``model.json`` under ``path``."""
        target = path / "model.json" if path.is_dir() or path.suffix == "" else path
        if target.parent:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "shrinkage_k": self.shrinkage_k,
                    "min_history": self.min_history,
                    "global_mean": self.global_mean,
                    "global_std": self.global_std,
                    "team_stats": self.team_stats,
                    "quantiles": list(self.quantiles),
                    "fitted": self._fitted,
                }
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> EmpiricalBayesBackend:
        """Restore from ``model.json`` in ``path``."""
        target = path / "model.json" if path.is_dir() else path
        data = json.loads(target.read_text(encoding="utf-8"))
        obj = cls(shrinkage_k=data["shrinkage_k"], min_history=data["min_history"])
        obj.global_mean = data["global_mean"]
        obj.global_std = data["global_std"]
        obj.team_stats = data["team_stats"]
        obj.quantiles = tuple(data["quantiles"])
        obj._fitted = data["fitted"]
        return obj


def identity_frame(team_ids: Sequence[str], epic_ids: Sequence[str] | None = None) -> pd.DataFrame:
    """Minimal feature frame with only ``team_id``, for tests and the Bayes backend."""
    idx = list(epic_ids) if epic_ids is not None else [str(i) for i in range(len(team_ids))]
    return pd.DataFrame({"team_id": list(team_ids)}, index=idx)
