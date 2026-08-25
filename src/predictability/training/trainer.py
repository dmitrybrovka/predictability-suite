"""Full-refit trainer and library train/predict."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import numpy as np

from predictability.core.config import AppConfig
from predictability.core.errors import EmptyTrainSetError, UsageError
from predictability.core.registry import MODELS, get_plugin
from predictability.core.schema import Epic, ModelArtifact, PredictabilityResult
from predictability.core.score import build_results
from predictability.core.slip import compute_slip
from predictability.factors.base import FactorContext
from predictability.factors.capacity_calendar import calendar_from_config
from predictability.factors.pipeline import build_matrix, effective_factor_specs, factor_set_hash
from predictability.models.empirical_bayes import EmpiricalBayesBackend
from predictability.store.sqlite import Store

logger = logging.getLogger(__name__)

_BACKENDS: dict[str, type[Any]] = {
    "empirical_bayes": EmpiricalBayesBackend,
}

# Fallback for source trees where entry points are not installed. Imported lazily
# so a missing optional extra fails in fit(), not at lookup.
_LAZY_BACKENDS = {
    "quantile_catboost": ("predictability.models.quantile_catboost", "QuantileCatBoostBackend"),
    "quantile_lightgbm": ("predictability.models.quantile_lightgbm", "QuantileLightGBMBackend"),
}


def _backend_cls(name: str) -> type[Any]:
    try:
        return cast("type[Any]", get_plugin(MODELS, name))
    except UsageError:
        if name in _BACKENDS:
            return _BACKENDS[name]
        if name not in _LAZY_BACKENDS:
            raise
        module_name, attr = _LAZY_BACKENDS[name]
        return cast("type[Any]", getattr(import_module(module_name), attr))


def _instantiate(name: str, config: AppConfig) -> Any:
    cls = _backend_cls(name)
    if name == "empirical_bayes":
        return EmpiricalBayesBackend(shrinkage_k=config.shrinkage_k, min_history=config.min_history)
    return cls()


def _warn_training_drift(cfg: AppConfig, artifact: ModelArtifact) -> None:
    """Config values baked into an artifact keep their training-time meaning; a
    later edit to them applies to the next `train`, not to existing artifacts."""
    if cfg.slip_unit != artifact.slip_unit:
        logger.warning(
            "config slip unit %r differs from the artifact's %r; scoring in the "
            "artifact's unit so features match training",
            cfg.slip_unit,
            artifact.slip_unit,
        )
    if cfg.min_history != artifact.min_history:
        logger.warning(
            "config min_history %d differs from the artifact's %d; cold_start uses "
            "the artifact's threshold. Retrain to apply the new one.",
            cfg.min_history,
            artifact.min_history,
        )


def _training_window(store: Store, artifact: ModelArtifact) -> list[Epic]:
    """Completed epics the artifact was trained on, so predict-time factors and
    team history describe the same data the model saw."""
    history = store.list_completed_epics()
    if artifact.data_cutoff is None:
        return history
    return [
        e
        for e in history
        if e.actual_completed_at is not None and e.actual_completed_at <= artifact.data_cutoff
    ]


def completed_for_train(epics: Sequence[Epic]) -> list[Epic]:
    return [
        e
        for e in epics
        if e.status == "done"
        and e.actual_completed_at is not None
        and e.committed_deadline is not None
    ]


def train(
    backend: str,
    db: Path | str,
    *,
    activate: bool = True,
    config: AppConfig | None = None,
) -> ModelArtifact:
    cfg = config or AppConfig.load()
    store = Store(db)
    epics = store.list_epics()
    train_epics = completed_for_train(epics)
    if not train_epics:
        raise EmptyTrainSetError("no completed epics with deadlines in the store")
    cal = calendar_from_config(cfg)
    ctx = FactorContext(
        calendar=cal,
        children=store.list_children(),
        dependencies=store.list_dependencies(),
        slip_unit=cfg.slip_unit,
    )
    x = build_matrix(train_epics, config=cfg, ctx=ctx, history=train_epics)
    slips = np.array(
        [compute_slip(e, unit=cfg.slip_unit, calendar=cal).value for e in train_epics],
        dtype=float,
    )
    model = _instantiate(backend, cfg)
    model.fit(
        x,
        slips,
        {
            "shrinkage_k": cfg.shrinkage_k,
            "min_history": cfg.min_history,
            "quantiles": cfg.quantiles,
        },
    )
    blob = store.artifact_dir() / str(uuid4())
    blob.mkdir(parents=True, exist_ok=True)
    model.save(blob)
    teams = {e.team_id for e in train_epics}
    cutoff = max(e.actual_completed_at for e in train_epics if e.actual_completed_at is not None)
    fhash = factor_set_hash(effective_factor_specs(cfg))
    return store.save_artifact(
        backend=backend,
        backend_version=getattr(model, "version", "1"),
        factor_set_hash=fhash,
        quantiles=list(cfg.quantiles),
        slip_unit=cfg.slip_unit,
        train_epic_count=len(train_epics),
        train_team_count=len(teams),
        data_cutoff=cutoff,
        blob_path=str(blob),
        activate=activate,
        min_history=cfg.min_history,
    )


def predict(
    db: Path | str,
    *,
    epics: Sequence[Epic] | None = None,
    model_id: str | None = None,
    config: AppConfig | None = None,
) -> list[PredictabilityResult]:
    cfg = config or AppConfig.load()
    store = Store(db)
    artifact = store.get_artifact(model_id)
    current_hash = factor_set_hash(effective_factor_specs(cfg))
    if current_hash != artifact.factor_set_hash:
        msg = (
            f"factor set changed since training: artifact {artifact.factor_set_hash!r} != "
            f"current config {current_hash!r}. Retrain, or restore the factor config "
            f"that produced the active artifact."
        )
        raise UsageError(msg)
    targets = [
        e
        for e in (list(epics) if epics is not None else store.list_epics(status="open"))
        if e.committed_deadline is not None and e.deadline_source is not None
    ]
    if not targets:
        return []
    _warn_training_drift(cfg, artifact)
    cal = calendar_from_config(cfg)
    ctx = FactorContext(
        calendar=cal,
        children=store.list_children(),
        dependencies=store.list_dependencies(),
        slip_unit=artifact.slip_unit,
    )
    history = _training_window(store, artifact)
    x = build_matrix(targets, config=cfg, ctx=ctx, history=history)
    keys = [f"{e.tracker}:{e.external_id}" for e in targets]
    x = x.reindex(keys)
    cls = _backend_cls(artifact.backend)
    loaded = cls.load(Path(artifact.blob_path))
    q = loaded.predict_quantiles(x, artifact.quantiles)
    p = loaded.predict_on_time_proba(x)
    return build_results(
        targets,
        quantiles=q,
        on_time=p,
        artifact=artifact,
        team_history=Counter(e.team_id for e in history),
        min_history=artifact.min_history,
        quantile_levels=artifact.quantiles,
    )
