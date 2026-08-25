"""YouTrack adapter. Default tests use fixtures, not live HTTP."""

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


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


class YouTrackAdapter:
    id = "youtrack"
    display_name = "YouTrack"

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = dict(config)
        self.team_field = str(config.get("team_field", "Team"))
        self.due_field = str(config.get("due_field", "due"))
        self.epic_types = {
            str(t).lower() for t in (config.get("epic_issue_types") or ["Feature", "Epic"])
        }
        self.epic_done = epic_done_rule(config)

    def test_connection(self) -> None:
        if self.config.get("fixture_path"):
            return
        if not os.environ.get("YOUTRACK_TOKEN"):
            raise AdapterAuthError("YOUTRACK_TOKEN is not set")

    def fetch(self, query: TrackerQuery) -> AdapterResult:
        path = query.get("fixture_path") or self.config.get("fixture_path")
        if not path:
            raise AdapterAuthError(
                "YouTrack live fetch is not used in default tests; set fixture_path"
            )
        payload = json.loads(Path(str(path)).read_text(encoding="utf-8"))
        issues = payload.get("issues") or payload.get("epics") or payload.get("features") or []
        epics: list[Epic] = []
        children: list[ChildIssue] = []
        deps: list[Dependency] = []
        for issue in issues:
            fields = issue.get("fields") or issue
            itype = str(fields.get("type") or fields.get("$type") or issue.get("kind") or "Feature")
            ident = str(issue.get("idReadable") or issue.get("id") or issue.get("external_id"))
            team = fields.get(self.team_field) or fields.get("team_id")
            if isinstance(team, dict):
                team = team.get("name")
            histories = []
            for hist in issue.get("activities") or issue.get("due_changelog") or []:
                histories.append(
                    (
                        _parse_dt(hist.get("timestamp") or hist.get("at") or hist.get("created"))
                        or datetime.now(UTC),
                        hist.get("added") or hist.get("due") or hist.get("to"),
                    )
                )
            current_due = fields.get(self.due_field) or fields.get("dueDate") or fields.get("due")
            committed, source = first_changelog_due(histories)
            if committed is None and current_due:
                committed = _parse_dt(str(current_due))
                source = "current_fallback"
            is_epic = itype.lower() in self.epic_types or issue.get("kind") in {"epic", "feature"}
            if is_epic:
                resolved = fields.get("resolved") or fields.get("actual_completed_at")
                epics.append(
                    Epic(
                        tracker="youtrack",
                        external_id=ident,
                        team_id=str(team or ""),
                        status="done" if resolved else "open",
                        committed_deadline=committed,
                        deadline_source=source,
                        actual_completed_at=_parse_dt(str(resolved)) if resolved else None,
                        created_at=_parse_dt(str(fields.get("created") or "2025-01-01T00:00:00Z"))
                        or datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                        title=fields.get("summary") or issue.get("summary"),
                        raw_payload_hash=payload_hash(issue),
                    )
                )
            else:
                child_resolved = fields.get("resolved") or fields.get("actual_completed_at")
                children.append(
                    ChildIssue(
                        tracker="youtrack",
                        external_id=ident,
                        epic_external_id=str(
                            issue.get("epic_external_id") or fields.get("parent") or ""
                        ),
                        team_id=str(team) if team else None,
                        status="done" if child_resolved else "open",
                        updated_at=datetime.now(UTC),
                        actual_completed_at=_parse_dt(str(child_resolved))
                        if child_resolved
                        else None,
                    )
                )
            for link in issue.get("links") or issue.get("dependencies") or []:
                if isinstance(link, dict) and link.get("to_external_id"):
                    deps.append(
                        Dependency(
                            tracker="youtrack",
                            from_external_id=ident,
                            to_external_id=str(link["to_external_id"]),
                            from_kind="epic",
                            to_team_id=link.get("to_team_id"),
                        )
                    )
        return AdapterResult(
            epics=apply_epic_done(epics, children, rule=self.epic_done),
            children=children,
            dependencies=deps,
        )
