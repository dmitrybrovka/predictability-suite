"""Jira adapter. Default tests use fixtures, not live HTTP."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predictability.adapters.base import (
    AdapterResult,
    TrackerQuery,
    apply_epic_done,
    epic_done_rule,
    first_changelog_due,
    payload_hash,
)
from predictability.core.errors import AdapterAuthError
from predictability.core.schema import ChildIssue, Dependency, Epic

_CANCELLED_STATUSES = {"cancelled", "canceled", "won't do", "wont do", "abandoned"}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


class JiraAdapter:
    """Jira epic adapter. Default tests use fixtures; live HTTP needs ``JIRA_TOKEN``."""

    id = "jira"
    display_name = "Jira"

    def __init__(self, config: Mapping[str, Any]) -> None:
        """Bind team/due fields, epic types, and ``epic_done``."""
        self.config = dict(config)
        self.team_field = str(config.get("team_field", "customfield_team"))
        self.due_field = str(config.get("due_field", "duedate"))
        self.epic_types = {str(t).lower() for t in (config.get("epic_issue_types") or ["Epic"])}
        self.epic_done = epic_done_rule(config)

    def test_connection(self) -> None:
        """Require ``JIRA_TOKEN`` unless ``fixture_path`` is set.

        Raises:
            AdapterAuthError: Live mode without a token.
        """
        if self.config.get("fixture_path"):
            return
        if not os.environ.get("JIRA_TOKEN"):
            raise AdapterAuthError("JIRA_TOKEN is not set")

    def fetch(self, query: TrackerQuery) -> AdapterResult:
        """Normalize fixture (or refuse live fetch in default tests).

        Raises:
            AdapterAuthError: No ``fixture_path`` in default CI mode.
        """
        path = query.get("fixture_path") or self.config.get("fixture_path")
        if not path:
            raise AdapterAuthError("Jira live fetch is not used in default tests; set fixture_path")
        payload = json.loads(Path(str(path)).read_text(encoding="utf-8"))
        return self._from_issues(payload.get("issues") or payload.get("epics") or [])

    def _from_issues(self, issues: list[dict[str, Any]]) -> AdapterResult:
        epics: list[Epic] = []
        children: list[ChildIssue] = []
        deps: list[Dependency] = []
        for issue in issues:
            fields = issue.get("fields") or issue
            itype = str(
                (fields.get("issuetype") or {}).get("name")
                if isinstance(fields.get("issuetype"), dict)
                else fields.get("issuetype", "Epic")
            )
            key = str(issue.get("key") or issue.get("external_id"))
            team = fields.get(self.team_field) or fields.get("team_id")
            if isinstance(team, dict):
                team = team.get("value") or team.get("name")
            histories = []
            for hist in (
                (issue.get("changelog") or {}).get("histories") or issue.get("due_changelog") or []
            ):
                if "items" in hist:
                    created = _parse_dt(hist.get("created")) or datetime.now(UTC)
                    for item in hist["items"]:
                        if str(item.get("field", "")).lower() in {self.due_field, "duedate", "due"}:
                            histories.append((created, item.get("to") or item.get("toString")))
                else:
                    histories.append(
                        (
                            _parse_dt(hist.get("at") or hist.get("created")) or datetime.now(UTC),
                            hist.get("due") or hist.get("to"),
                        )
                    )
            current_due = fields.get(self.due_field) or fields.get("due")
            committed, source = first_changelog_due(histories)
            if committed is None and current_due:
                committed = _parse_dt(str(current_due))
                source = "current_fallback"
            is_epic = itype.lower() in self.epic_types or issue.get("kind") == "epic"
            if is_epic:
                resolution = fields.get("resolutiondate") or fields.get("actual_completed_at")
                status_name = fields.get("status")
                if isinstance(status_name, dict):
                    status_name = status_name.get("name", "open")
                cancelled = str(status_name).lower() in _CANCELLED_STATUSES
                epics.append(
                    Epic(
                        tracker="jira",
                        external_id=key,
                        team_id=str(team or ""),
                        status="cancelled" if cancelled else ("done" if resolution else "open"),
                        committed_deadline=committed,
                        deadline_source=source,
                        actual_completed_at=_parse_dt(str(resolution)) if resolution else None,
                        created_at=_parse_dt(str(fields.get("created") or "2025-01-01T00:00:00Z"))
                        or datetime.now(UTC),
                        updated_at=_parse_dt(str(fields.get("updated") or "2025-01-01T00:00:00Z"))
                        or datetime.now(UTC),
                        title=fields.get("summary") or fields.get("title"),
                        raw_payload_hash=payload_hash(issue),
                    )
                )
            else:
                parent = fields.get("parent") or issue.get("epic_external_id")
                if isinstance(parent, dict):
                    parent = parent.get("key")
                children.append(
                    ChildIssue(
                        tracker="jira",
                        external_id=key,
                        epic_external_id=str(parent or ""),
                        team_id=str(team) if team else None,
                        status=str(fields.get("status") or "open"),
                        updated_at=datetime.now(UTC),
                        actual_completed_at=_parse_dt(fields.get("resolutiondate")),
                    )
                )
            for link in fields.get("issuelinks") or issue.get("dependencies") or []:
                other = (
                    (link.get("inwardIssue") or link.get("outwardIssue") or {}).get("key")
                    if isinstance(link, dict)
                    else None
                )
                if isinstance(link, dict) and link.get("to_external_id"):
                    deps.append(
                        Dependency(
                            tracker="jira",
                            from_external_id=key,
                            to_external_id=str(link["to_external_id"]),
                            from_kind="epic",
                            to_team_id=link.get("to_team_id"),
                        )
                    )
                elif other:
                    deps.append(
                        Dependency(
                            tracker="jira",
                            from_external_id=key,
                            to_external_id=str(other),
                            from_kind="epic",
                        )
                    )
        return AdapterResult(
            epics=apply_epic_done(epics, children, rule=self.epic_done),
            children=children,
            dependencies=deps,
        )
