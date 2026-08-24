# Model backend protocol

**Feature**: `001-team-work-predictability`  
**Consumers**: `train`, `predict`, `evaluate` (walk-forward), config `model.backend`

## Purpose

Swap learning libraries without changing adapters or factors. Requirement 4. **Bias is a first-class backend**, not only a GBM feature.

## Registration

Entry point group: `predictability.models`

| Name | Extra | Role |
|------|-------|------|
| `empirical_bayes` | core | Team slip shrinkage (bias baseline) |
| `quantile_catboost` | `[catboost]` | Quantile GBM |
| `quantile_lightgbm` | `[gbm]` | Quantile GBM |

Do **not** collapse CatBoost and LightGBM into one registry name.

## Interface

```python
class ModelBackend(Protocol):
    name: str
    version: str
    quantiles: Sequence[float]  # default (0.5, 0.9)

    def fit(self, X: FeatureFrame, slip: ndarray, meta: Mapping[str, Any]) -> Self: ...

    def partial_fit(self, X, slip, meta) -> Self:
        """Optional. v1 trainer uses full refit if missing."""

    def predict_quantiles(self, X: FeatureFrame, quantiles: Sequence[float] | None = None) -> ndarray:
        """Shape (n_epics, n_quantiles)."""

    def predict_on_time_proba(self, X: FeatureFrame) -> ndarray:
        """P(slip <= 0)."""

    def save(self, path: Path) -> None: ...
    @classmethod
    def load(cls, path: Path) -> Self: ...
```

## Empirical Bayes

`μ_t = w_t * mean_t + (1-w_t) * mean_global`, `w_t = n_t / (n_t + k)`.

Quantiles from Gaussian or pooled residuals (document in artifact).  
`n_t < min_history` ⇒ global, `cold_start=true`.

## CatBoost / LightGBM

- Input: factor matrix (includes `team_bias` columns when that factor is on; `team_id` may be categorical)
- Quantile objective (one model per quantile or native multi-quantile)
- Missing extra: clear error to `pip install predictability[catboost]` or `[gbm]`

## Evaluation contract (CLI `evaluate`)

**Walk-forward only.** Does **not** call `ModelArtifact.is_active`. Does **not** write `is_active`.

1. Sort completed epics by `actual_completed_at`
2. Expanding origin, `min_train` (default 200 epics), horizon (default 14 days or 30 epics)
3. At each origin: fit factors+backend on past, score future
4. Metrics: MAE slip, pinball per quantile, [p50,p90] coverage, Brier on-time

Primary rank: **p90 pinball**; tie-break **Brier on-time**.

`empirical_bayes` SHOULD be included in default `evaluate` backend list so bias is always compared.

## Serving vs evaluate

| Command | Fits? | Uses active artifact? |
|---------|-------|------------------------|
| `train` | yes, once | becomes active (default) |
| `predict` | no | **yes** |
| `evaluate` | yes, per fold | **no** |

## Swap procedure

1. `predictability evaluate --backends empirical_bayes,quantile_catboost,quantile_lightgbm`
2. `predictability train --backend <winner>` (activates)
3. `predict` `backend` field MUST equal that artifact — contract test
