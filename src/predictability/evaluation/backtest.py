"""Walk-forward evaluation. Does not read or write artifact is_active."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np

from predictability.core.calendar import CapacityCalendar
from predictability.core.config import AppConfig
from predictability.core.errors import ExtraMissingError, PredictabilityError
from predictability.core.schema import Epic, EvaluationReport, EvaluationRow
from predictability.core.slip import compute_slip
from predictability.evaluation.metrics import brier, interval_coverage, mae, pinball
from predictability.factors.base import FactorContext
from predictability.factors.capacity_calendar import calendar_from_config
from predictability.factors.pipeline import build_matrix
from predictability.store.sqlite import Store
from predictability.training.trainer import _instantiate, completed_for_train


def evaluate(
    db: Path | str,
    backends: Sequence[str],
    *,
    config: AppConfig | None = None,
    min_train: int = 50,
    horizon_epics: int = 30,
) -> EvaluationReport:
    """Walk-forward compare ``backends`` on stored completed epics.

    Does not read or write ``is_active``. A missing GBM extra becomes an error
    row; other backends still complete.

    Args:
        db: SQLite path.
        backends: Registry names to evaluate.
        config: Factor/model settings.
        min_train: Expanding origin size (shrunk if the history is smaller).
        horizon_epics: Future epics scored at each origin.

    Returns:
        Side-by-side metrics (MAE, pinball, Brier, interval coverage).
    """
    cfg = config or AppConfig.load()
    store = Store(db)
    # Intentionally do not touch is_active.
    epics = sorted(
        completed_for_train(store.list_epics()),
        key=lambda e: e.actual_completed_at or datetime.min.replace(tzinfo=UTC),
    )
    cal = calendar_from_config(cfg)
    ctx = FactorContext(
        calendar=cal,
        children=store.list_children(),
        dependencies=store.list_dependencies(),
        slip_unit=cfg.slip_unit,
    )
    rows: list[EvaluationRow] = []
    cutoff = epics[-1].actual_completed_at if epics else None
    min_train = min(min_train, max(8, len(epics) // 3)) if epics else min_train
    for name in backends:
        try:
            rows.append(
                _eval_backend(
                    name,
                    epics,
                    cfg=cfg,
                    cal=cal,
                    ctx=ctx,
                    min_train=min_train,
                    horizon_epics=horizon_epics,
                )
            )
        except ExtraMissingError as exc:
            rows.append(EvaluationRow(backend=name, error=str(exc)))
        except PredictabilityError as exc:
            rows.append(EvaluationRow(backend=name, error=str(exc)))
    return EvaluationReport(
        id=str(uuid4()),
        created_at=datetime.now(UTC),
        split={"min_train": min_train, "horizon_epics": horizon_epics, "origins": "expanding"},
        dataset_cutoff=cutoff,
        rows=rows,
    )


def _eval_backend(
    name: str,
    epics: list[Epic],
    *,
    cfg: AppConfig,
    cal: CapacityCalendar,
    ctx: FactorContext,
    min_train: int,
    horizon_epics: int,
) -> EvaluationRow:
    actuals: list[float] = []
    pred_exp: list[float] = []
    pred_p50: list[float] = []
    pred_p90: list[float] = []
    proba: list[float] = []
    origin = min_train
    while origin < len(epics):
        train_set = epics[:origin]
        test_set = epics[origin : origin + horizon_epics]
        if not test_set:
            break
        x_train = build_matrix(train_set, config=cfg, ctx=ctx, history=train_set)
        y_train = np.array(
            [compute_slip(e, unit=cfg.slip_unit, calendar=cal).value for e in train_set],
            dtype=float,
        )
        model = _instantiate(name, cfg)
        model.fit(
            x_train,
            y_train,
            {
                "shrinkage_k": cfg.shrinkage_k,
                "min_history": cfg.min_history,
                "quantiles": (0.5, 0.9),
            },
        )
        x_test = build_matrix(test_set, config=cfg, ctx=ctx, history=train_set)
        keys = [f"{e.tracker}:{e.external_id}" for e in test_set]
        x_test = x_test.reindex(keys)
        q = model.predict_quantiles(x_test, (0.5, 0.9))
        p = model.predict_on_time_proba(x_test)
        for i, epic in enumerate(test_set):
            actual = compute_slip(epic, unit=cfg.slip_unit, calendar=cal).value
            actuals.append(actual)
            pred_exp.append(float(q[i, 0]))
            pred_p50.append(float(q[i, 0]))
            pred_p90.append(float(q[i, 1]))
            proba.append(float(p[i]))
        origin += horizon_epics
    a = np.array(actuals, dtype=float)
    e = np.array(pred_exp, dtype=float)
    p50 = np.array(pred_p50, dtype=float)
    p90 = np.array(pred_p90, dtype=float)
    pr = np.array(proba, dtype=float)
    on_time = (a <= 0).astype(float)
    return EvaluationRow(
        backend=name,
        mae_slip=mae(a, e),
        pinball={"0.5": pinball(a, p50, 0.5), "0.9": pinball(a, p90, 0.9)},
        coverage_p50_p90=interval_coverage(a, p50, p90),
        brier_on_time=brier(on_time, pr),
        n_eval=len(actuals),
        artifact_id=None,
    )
