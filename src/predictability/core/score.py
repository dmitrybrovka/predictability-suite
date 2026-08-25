"""Assemble PredictabilityResult rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from predictability.core.schema import Epic, ModelArtifact, PredictabilityResult


def build_results(
    epics: Sequence[Epic],
    *,
    quantiles: np.ndarray,
    on_time: np.ndarray,
    artifact: ModelArtifact,
    team_history: Mapping[str, int],
    min_history: int,
    quantile_levels: Sequence[float] = (0.5, 0.9),
) -> list[PredictabilityResult]:
    """Assemble result rows. `team_history` counts completed epics per team in
    the artifact's training window, so cold start does not depend on the backend."""
    results: list[PredictabilityResult] = []
    q_keys = [str(q) for q in quantile_levels]
    for i, epic in enumerate(epics):
        if epic.committed_deadline is None or epic.deadline_source is None:
            continue
        qmap = {q_keys[j]: float(quantiles[i, j]) for j in range(len(q_keys))}
        expected = float(qmap.get("0.5", next(iter(qmap.values()))))
        n = int(team_history.get(epic.team_id, 0))
        cold = n < min_history
        results.append(
            PredictabilityResult(
                tracker=epic.tracker,
                external_id=epic.external_id,
                team_id=epic.team_id,
                committed_deadline=epic.committed_deadline,
                deadline_source=epic.deadline_source,
                expected_slip=expected,
                quantiles=qmap,
                on_time_probability=float(on_time[i]),
                cold_start=cold,
                team_history_n=n,
                model_id=str(artifact.id),
                backend=artifact.backend,
                factor_set_hash=artifact.factor_set_hash,
            )
        )
    return results
