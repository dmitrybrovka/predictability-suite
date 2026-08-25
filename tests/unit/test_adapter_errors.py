from pathlib import Path

import pytest

from predictability.adapters.jira import JiraAdapter
from predictability.core.errors import AdapterAuthError
from predictability.ingest import ingest


def test_empty_fetch() -> None:
    from predictability.adapters.mock import MockAdapter

    result = MockAdapter({}).fetch({"seed": 1, "n_teams": 1, "n_epics": 0})
    assert result.epics == []
    assert result.children == []


def test_missing_team_skipped(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text(
        '{"epics":[{"external_id":"E1","status":"done","due":"2026-01-01T00:00:00Z",'
        '"actual_completed_at":"2026-01-02T00:00:00Z","created_at":"2025-01-01T00:00:00Z"}]}',
        encoding="utf-8",
    )
    report = ingest("mock", {"fixture_path": str(path)}, tmp_path / "db.sqlite")
    assert report.imported == 0
    assert report.skipped_unmapped_team == 1


def test_jira_auth_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    with pytest.raises(AdapterAuthError):
        JiraAdapter({}).test_connection()
