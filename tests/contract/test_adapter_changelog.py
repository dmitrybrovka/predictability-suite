import json
from pathlib import Path

import pytest

from predictability.adapters.jira import JiraAdapter
from predictability.adapters.mock import MockAdapter
from predictability.core.errors import UsageError


def test_changelog_first_due() -> None:
    root = Path(__file__).resolve().parents[1] / "fixtures"
    jira = JiraAdapter(
        {"team_field": "customfield_team", "fixture_path": str(root / "jira/epic_changelog.json")}
    )
    result = jira.fetch({})
    epic = result.epics[0]
    assert epic.deadline_source == "changelog"
    deadline = epic.committed_deadline
    assert deadline is not None
    assert deadline.day == 15


def test_fallback_without_changelog(tmp_path: Path) -> None:
    path = tmp_path / "nolog.json"
    path.write_text(
        '{"epics":[{"external_id":"E1","team_id":"t","status":"done","due":"2026-03-01T00:00:00Z",'
        '"actual_completed_at":"2026-03-05T00:00:00Z","created_at":"2026-01-01T00:00:00Z"}]}',
        encoding="utf-8",
    )
    result = MockAdapter({}).fetch({"fixture_path": str(path)})
    assert result.epics[0].deadline_source == "current_fallback"
    fallback = result.epics[0].committed_deadline
    assert fallback is not None
    assert fallback.month == 3


def _epic_done_fixture(tmp_path: Path) -> Path:
    """Epic with no resolution date of its own and two completed children."""
    path = tmp_path / "epic_done.json"
    path.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "key": "E-1",
                        "kind": "epic",
                        "fields": {
                            "issuetype": {"name": "Epic"},
                            "customfield_team": "alpha",
                            "duedate": "2026-03-01T00:00:00Z",
                            "status": {"name": "In Progress"},
                            "created": "2026-01-01T00:00:00Z",
                        },
                    },
                    {
                        "key": "C-1",
                        "fields": {
                            "issuetype": "Story",
                            "parent": {"key": "E-1"},
                            "resolutiondate": "2026-03-04T00:00:00Z",
                        },
                    },
                    {
                        "key": "C-2",
                        "fields": {
                            "issuetype": "Story",
                            "parent": {"key": "E-1"},
                            "resolutiondate": "2026-03-06T00:00:00Z",
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("rule", "expect_done", "expect_day"),
    [("own", False, None), ("children", True, 6), ("own_then_children", True, 6)],
)
def test_epic_done_rules(
    tmp_path: Path, rule: str, expect_done: bool, expect_day: int | None
) -> None:
    path = _epic_done_fixture(tmp_path)
    adapter = JiraAdapter(
        {"team_field": "customfield_team", "fixture_path": str(path), "epic_done": rule}
    )
    epic = adapter.fetch({}).epics[0]
    assert (epic.status == "done") is expect_done
    if expect_day is None:
        assert epic.actual_completed_at is None
    else:
        assert epic.actual_completed_at is not None
        assert epic.actual_completed_at.day == expect_day


def test_epic_done_own_wins_over_children(tmp_path: Path) -> None:
    raw = json.loads(_epic_done_fixture(tmp_path).read_text(encoding="utf-8"))
    raw["issues"][0]["fields"]["resolutiondate"] = "2026-03-02T00:00:00Z"
    path = tmp_path / "own_first.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    epic = (
        JiraAdapter({"team_field": "customfield_team", "fixture_path": str(path)})
        .fetch({})
        .epics[0]
    )
    assert epic.actual_completed_at is not None
    assert epic.actual_completed_at.day == 2


def test_unknown_epic_done_rule_is_usage_error() -> None:
    with pytest.raises(UsageError, match="epic_done"):
        JiraAdapter({"epic_done": "whenever"})
