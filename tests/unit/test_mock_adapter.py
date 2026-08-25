from pathlib import Path

from predictability.adapters.mock import MockAdapter


def test_mock_synthetic_query() -> None:
    adapter = MockAdapter({})
    result = adapter.fetch({"seed": 7, "n_teams": 2, "n_epics": 20})
    done = [e for e in result.epics if e.status == "done"]
    open_epics = [e for e in result.epics if e.status == "open"]
    assert len(done) == 20
    assert len(open_epics) == 5
    assert {e.team_id for e in result.epics} == {"team-0", "team-1"}
    assert all(e.committed_deadline is not None for e in result.epics)
    assert {c.epic_external_id for c in result.children} <= {e.external_id for e in done}
    assert result.dependencies
    assert all(d.to_team_id == "team-0" for d in result.dependencies)


def test_mock_empty_query_yields_nothing() -> None:
    result = MockAdapter({}).fetch({"seed": 1, "n_teams": 2, "n_epics": 0})
    assert result.epics == []
    assert result.children == []
    assert result.dependencies == []


def test_mock_fixture_changelog(tmp_path: Path) -> None:
    path = tmp_path / "fix.json"
    path.write_text(
        """
{
  "epics": [
    {
      "external_id": "E1",
      "team_id": "alpha",
      "status": "done",
      "due": "2026-02-01T00:00:00Z",
      "actual_completed_at": "2026-02-10T00:00:00Z",
      "created_at": "2025-12-01T00:00:00Z",
      "due_changelog": [
        {"at": "2025-12-01T00:00:00Z", "due": "2026-01-15T00:00:00Z"},
        {"at": "2026-01-02T00:00:00Z", "due": "2026-02-01T00:00:00Z"}
      ]
    }
  ]
}
""",
        encoding="utf-8",
    )
    result = MockAdapter({}).fetch({"fixture_path": str(path)})
    assert result.epics[0].deadline_source == "changelog"
    deadline = result.epics[0].committed_deadline
    assert deadline is not None
    assert deadline.day == 15
