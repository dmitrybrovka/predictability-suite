"""Per-team slip bias features. No leakage from future completions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import pandas as pd

from predictability.core.calendar import CapacityCalendar
from predictability.core.schema import Epic
from predictability.core.slip import compute_slip
from predictability.factors.base import FactorContext, FeatureFrame

_COLUMNS = (
    "team_id",
    "team_n",
    "team_mean_slip",
    "team_std_slip",
    "global_mean_slip",
    "shrinkage_w",
)


class TeamBiasFactor:
    name = "team_bias"
    version = "1.0.0"

    def __init__(self, *, shrinkage_k: float = 10.0) -> None:
        self.shrinkage_k = shrinkage_k
        self._slips: list[tuple[str, datetime, float]] = []

    def fit(self, epics: Sequence[Epic], ctx: FactorContext) -> TeamBiasFactor:
        cal = ctx.calendar or CapacityCalendar()
        self._slips = []
        for epic in epics:
            if epic.actual_completed_at is None or epic.committed_deadline is None:
                continue
            if epic.status != "done":
                continue
            slip = compute_slip(epic, unit=ctx.slip_unit, calendar=cal)
            self._slips.append((epic.team_id, epic.actual_completed_at, slip.value))
        return self

    def transform(self, epics: Sequence[Epic], ctx: FactorContext) -> FeatureFrame:
        rows = []
        for epic in epics:
            cutoff = epic.committed_deadline
            past = [
                v
                for team, completed, v in self._slips
                if team == epic.team_id and cutoff is not None and completed < cutoff
            ]
            all_past = [
                v for _t, completed, v in self._slips if cutoff is not None and completed < cutoff
            ]
            n = len(past)
            team_mean = float(sum(past) / n) if n else 0.0
            if n > 1:
                var = sum((x - team_mean) ** 2 for x in past) / (n - 1)
                team_std = var**0.5
            else:
                team_std = 0.0
            g_n = len(all_past)
            g_mean = float(sum(all_past) / g_n) if g_n else 0.0
            w = n / (n + self.shrinkage_k) if (n + self.shrinkage_k) else 0.0
            rows.append(
                {
                    "epic_id": f"{epic.tracker}:{epic.external_id}",
                    "team_id": epic.team_id,
                    "team_n": n,
                    "team_mean_slip": team_mean,
                    "team_std_slip": team_std,
                    "global_mean_slip": g_mean,
                    "shrinkage_w": w,
                }
            )
        if not rows:
            return pd.DataFrame(columns=list(_COLUMNS), index=pd.Index([], name="epic_id"))
        return pd.DataFrame(rows).set_index("epic_id")
