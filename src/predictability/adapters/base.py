"""Tracker adapter protocol."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, TypedDict

from predictability.core.errors import UsageError
from predictability.core.schema import ChildIssue, DeadlineSource, Dependency, Epic

EpicDoneRule = Literal["own", "children", "own_then_children"]
EPIC_DONE_RULES: tuple[EpicDoneRule, ...] = ("own", "children", "own_then_children")


class TrackerQuery(TypedDict, total=False):
    jql: str
    youtrack_query: str
    project: str
    updated_since: str
    fixture_path: str
    seed: int
    n_teams: int
    n_epics: int


@dataclass
class AdapterResult:
    epics: list[Epic] = field(default_factory=list)
    children: list[ChildIssue] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)


class TrackerAdapter(Protocol):
    id: str
    display_name: str

    def __init__(self, config: Mapping[str, Any]) -> None: ...

    def test_connection(self) -> None: ...

    def fetch(self, query: TrackerQuery) -> AdapterResult: ...


def first_changelog_due(
    entries: list[tuple[datetime, str | None]],
) -> tuple[datetime | None, DeadlineSource]:
    """Oldest-first changelog; first non-null due wins."""
    ordered = sorted(entries, key=lambda item: item[0])
    for _ts, due in ordered:
        if due:
            parsed = datetime.fromisoformat(due.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed, "changelog"
    return None, "current_fallback"


def epic_done_rule(config: Mapping[str, Any]) -> EpicDoneRule:
    rule = str(config.get("epic_done", "own_then_children"))
    if rule not in EPIC_DONE_RULES:
        msg = f"epic_done must be one of {', '.join(EPIC_DONE_RULES)}; got {rule!r}"
        raise UsageError(msg)
    return rule


def apply_epic_done(
    epics: Sequence[Epic],
    children: Sequence[ChildIssue],
    *,
    rule: EpicDoneRule,
) -> list[Epic]:
    """Resolve completion per the `epic_done` rule.

    `children` means "all children complete, timestamped by the last one"; an epic
    with no children is never complete under that rule. An epic without a
    completion timestamp is open, so `status=done` always implies a known
    `actual_completed_at`.
    """
    by_epic: dict[str, list[ChildIssue]] = {}
    for child in children:
        by_epic.setdefault(child.epic_external_id, []).append(child)
    out: list[Epic] = []
    for epic in epics:
        kids = [c.actual_completed_at for c in by_epic.get(epic.external_id, [])]
        all_done = bool(kids) and all(ts is not None for ts in kids)
        children_done = max(ts for ts in kids if ts is not None) if all_done else None
        if rule == "own":
            completed = epic.actual_completed_at
        elif rule == "children":
            completed = children_done
        else:
            completed = epic.actual_completed_at or children_done
        status = epic.status if epic.status == "cancelled" else ("done" if completed else "open")
        out.append(epic.model_copy(update={"actual_completed_at": completed, "status": status}))
    return out


def payload_hash(payload: Any) -> str:
    """Stable short digest of a raw tracker item, for change detection on re-ingest."""
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
