"""Build a combined feature matrix from enabled factors."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import cast

import pandas as pd

from predictability.core.config import AppConfig
from predictability.core.errors import UsageError
from predictability.core.registry import FACTORS, get_plugin
from predictability.core.schema import ChildIssue, Dependency, Epic, FactorSpec
from predictability.factors.base import Factor, FactorContext, FeatureFrame
from predictability.factors.capacity_calendar import CapacityCalendarFactor
from predictability.factors.cross_team_deps import CrossTeamDepsFactor
from predictability.factors.team_bias import TeamBiasFactor

_BUILTINS: dict[str, type] = {
    "team_bias": TeamBiasFactor,
    "capacity_calendar": CapacityCalendarFactor,
    "cross_team_deps": CrossTeamDepsFactor,
}


def factor_set_hash(specs: Sequence[FactorSpec]) -> str:
    """Stable short hash of enabled factor names, versions, and params."""
    payload = [
        {"name": s.name, "enabled": s.enabled, "version": s.version, "params": s.params}
        for s in specs
        if s.enabled
    ]
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def effective_factor_specs(config: AppConfig) -> list[FactorSpec]:
    """Specs `build_matrix` will actually apply, including the team_bias default."""
    enabled = [s for s in config.factors if s.enabled]
    if enabled:
        return enabled
    return [FactorSpec(name="team_bias", enabled=True, params=config.factor_params("team_bias"))]


def instantiate(spec: FactorSpec) -> Factor:
    """Construct a built-in or plugin factor.

    Raises:
        KeyError: Unknown factor name.
    """
    try:
        cls = get_plugin(FACTORS, spec.name)
    except UsageError:
        cls = _BUILTINS.get(spec.name)
    if cls is None:
        msg = f"unknown factor {spec.name}"
        raise KeyError(msg)
    if spec.name == "team_bias":
        return TeamBiasFactor(shrinkage_k=float(spec.params.get("shrinkage_k", 10)))
    if spec.name == "capacity_calendar":
        return CapacityCalendarFactor(spec.params)
    if spec.name == "cross_team_deps":
        return CrossTeamDepsFactor(spec.params)
    return cast(Factor, cls(**spec.params) if spec.params else cls())


def build_matrix(
    epics: Sequence[Epic],
    *,
    config: AppConfig,
    ctx: FactorContext,
    history: Sequence[Epic] | None = None,
    children: Sequence[ChildIssue] | None = None,
    dependencies: Sequence[Dependency] | None = None,
) -> FeatureFrame:
    """Rows for `epics`, with factors fitted on `history` (defaults to `epics`).

    Callers scoring open or held-out epics MUST pass the completed history they
    trained on, otherwise factors fit on rows that carry no slip and every
    history-derived column collapses to zero.
    """
    ctx.children = list(children or ctx.children)
    ctx.dependencies = list(dependencies or ctx.dependencies)
    targets = list(epics)
    fit_epics = list(history) if history is not None else targets
    frames: list[pd.DataFrame] = []
    index = [f"{e.tracker}:{e.external_id}" for e in targets]
    base = pd.DataFrame({"team_id": [e.team_id for e in targets]}, index=index)
    frames.append(base)
    for spec in effective_factor_specs(config):
        factor = instantiate(spec)
        factor.fit(fit_epics, ctx)
        frames.append(factor.transform(targets, ctx))
    out = frames[0]
    for extra in frames[1:]:
        cols = [c for c in extra.columns if c != "team_id"]
        out = out.join(extra[cols], how="left")
    return out.fillna(0.0)
