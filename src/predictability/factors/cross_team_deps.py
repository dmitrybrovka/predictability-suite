"""Cross-team dependency load: epic union child links, deduped by team_id."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Sequence
from typing import Any

import pandas as pd

from predictability.core.schema import ChildIssue, Epic
from predictability.factors.base import FactorContext, FeatureFrame

logger = logging.getLogger(__name__)

_COLUMNS = (
    "foreign_team_blocker_count",
    "dep_depth",
    "child_count",
    "open_child_count",
    "child_estimate_sum",
    "foreign_child_team_count",
)


class CrossTeamDepsFactor:
    name = "cross_team_deps"
    version = "1.0.0"

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.max_depth = int((params or {}).get("max_depth", 4))

    def fit(self, epics: Sequence[Epic], ctx: FactorContext) -> CrossTeamDepsFactor:
        return self

    def transform(self, epics: Sequence[Epic], ctx: FactorContext) -> FeatureFrame:
        children = list(ctx.children)
        deps = list(ctx.dependencies)
        child_by_id = {c.external_id: c for c in children}
        epic_by_id = {e.external_id: e for e in epics}
        children_of: dict[str, list[ChildIssue]] = defaultdict(list)
        for child in children:
            children_of[child.epic_external_id].append(child)

        graph: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for dep in deps:
            graph[dep.from_external_id].append((dep.to_external_id, dep.to_team_id))

        rows = []
        truncated = False
        for epic in epics:
            foreign: set[str] = set()
            starts = [
                epic.external_id,
                *(c.external_id for c in children_of.get(epic.external_id, [])),
            ]
            seen: set[str] = set()
            reached = 0
            q: deque[tuple[str, int]] = deque((s, 0) for s in starts)
            while q:
                node, depth = q.popleft()
                if depth > self.max_depth:
                    truncated = True
                    continue
                if node in seen:
                    continue
                seen.add(node)
                reached = max(reached, depth)
                for nxt, to_team in graph.get(node, []):
                    team = to_team
                    if team is None and nxt in epic_by_id:
                        team = epic_by_id[nxt].team_id
                    if team is None and nxt in child_by_id:
                        team = child_by_id[nxt].team_id
                    if team and team != epic.team_id:
                        foreign.add(team)
                    q.append((nxt, depth + 1))
            kids = children_of.get(epic.external_id, [])
            open_kids = [c for c in kids if c.actual_completed_at is None]
            foreign_child_teams = {
                c.team_id for c in kids if c.team_id and c.team_id != epic.team_id
            }
            rows.append(
                {
                    "epic_id": f"{epic.tracker}:{epic.external_id}",
                    "foreign_team_blocker_count": float(len(foreign)),
                    "dep_depth": float(reached),
                    "child_count": float(len(kids)),
                    "open_child_count": float(len(open_kids)),
                    "child_estimate_sum": float(sum(c.estimate or 0.0 for c in kids)),
                    "foreign_child_team_count": float(len(foreign_child_teams)),
                }
            )
        if truncated:
            # Cycles and very deep chains are expected in real trackers: warn, keep going.
            logger.warning(
                "cross_team_deps: dependency walk hit max_depth=%d; deeper links ignored",
                self.max_depth,
            )
        if not rows:
            return pd.DataFrame(columns=list(_COLUMNS), index=pd.Index([], name="epic_id"))
        return pd.DataFrame(rows).set_index("epic_id")
