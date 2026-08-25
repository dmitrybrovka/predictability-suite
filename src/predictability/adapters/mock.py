"""Mock adapter: fixture JSON or synthetic generator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predictability.adapters.base import (
    AdapterResult,
    TrackerQuery,
    first_changelog_due,
    payload_hash,
)
from predictability.core.schema import ChildIssue, Dependency, Epic
from predictability.core.synthetic import generate_epics


class MockAdapter:
    id = "mock"
    display_name = "Mock"

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = dict(config)

    def test_connection(self) -> None:
        return None

    def fetch(self, query: TrackerQuery) -> AdapterResult:
        fixture = query.get("fixture_path") or self.config.get("fixture_path")
        if fixture:
            return self._from_fixture(Path(str(fixture)))
        seed = int(query.get("seed", self.config.get("seed", 42)))
        n_teams = int(query.get("n_teams", self.config.get("n_teams", 3)))
        n_epics = int(query.get("n_epics", self.config.get("n_epics", 120)))
        epics, children, deps = generate_epics(seed=seed, n_teams=n_teams, n_epics=n_epics)
        return AdapterResult(epics=epics, children=children, dependencies=deps)

    def _from_fixture(self, path: Path) -> AdapterResult:
        raw = json.loads(path.read_text(encoding="utf-8"))
        epics: list[Epic] = []
        children: list[ChildIssue] = []
        deps: list[Dependency] = []
        for item in raw.get("epics") or []:
            changelog = [
                (datetime.fromisoformat(e["at"].replace("Z", "+00:00")), e.get("due"))
                for e in item.get("due_changelog") or []
            ]
            current = item.get("due")
            committed, source = first_changelog_due(changelog)
            if committed is None and current:
                committed = datetime.fromisoformat(str(current).replace("Z", "+00:00"))
                source = "current_fallback"
            actual = item.get("actual_completed_at")
            # Unmapped teams and missing deadlines are reported and dropped by
            # ingest, so emit the row and let one place own the counters.
            epics.append(
                Epic(
                    tracker="mock",
                    external_id=str(item["external_id"]),
                    team_id=str(item.get("team_id") or ""),
                    status=item.get("status", "done"),
                    committed_deadline=committed,
                    deadline_source=source,
                    actual_completed_at=(
                        datetime.fromisoformat(str(actual).replace("Z", "+00:00"))
                        if actual
                        else None
                    ),
                    created_at=datetime.fromisoformat(
                        str(item.get("created_at", "2025-01-01T00:00:00+00:00")).replace(
                            "Z", "+00:00"
                        )
                    ),
                    updated_at=datetime.now(UTC),
                    title=item.get("title"),
                    raw_payload_hash=payload_hash(item),
                )
            )
        for item in raw.get("children") or []:
            children.append(
                ChildIssue.model_validate({**item, "tracker": item.get("tracker", "mock")})
            )
        for item in raw.get("dependencies") or []:
            deps.append(Dependency.model_validate({**item, "tracker": item.get("tracker", "mock")}))
        return AdapterResult(epics=epics, children=children, dependencies=deps)
