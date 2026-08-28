"""Evaluation metrics."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def mae(actual: NDArray[np.floating], predicted: NDArray[np.floating]) -> float:
    """Mean absolute error of predicted vs actual slip. Empty input is NaN."""
    if len(actual) == 0:
        return float("nan")
    return float(np.mean(np.abs(actual - predicted)))


def pinball(
    actual: NDArray[np.floating], predicted: NDArray[np.floating], quantile: float
) -> float:
    """Pinball (quantile) loss. Smaller is better. Empty input is NaN."""
    if len(actual) == 0:
        return float("nan")
    delta = actual - predicted
    return float(np.mean(np.maximum(quantile * delta, (quantile - 1.0) * delta)))


def brier(actual_on_time: NDArray[np.floating], proba: NDArray[np.floating]) -> float:
    """Brier score of on-time probability vs 0/1 outcome. Empty input is NaN."""
    if len(actual_on_time) == 0:
        return float("nan")
    return float(np.mean((proba - actual_on_time) ** 2))


def interval_coverage(
    actual: NDArray[np.floating],
    q_lo: NDArray[np.floating],
    q_hi: NDArray[np.floating],
) -> float:
    """Fraction of actuals inside ``[q_lo, q_hi]``. Empty input is NaN."""
    if len(actual) == 0:
        return float("nan")
    inside = (actual >= q_lo) & (actual <= q_hi)
    return float(np.mean(inside))
