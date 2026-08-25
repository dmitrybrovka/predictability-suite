from pathlib import Path

from predictability.adapters.jira import JiraAdapter
from predictability.adapters.youtrack import YouTrackAdapter


def test_jira_and_youtrack_same_canonical_fields() -> None:
    root = Path(__file__).resolve().parents[1] / "fixtures"
    jira = JiraAdapter(
        {"team_field": "customfield_team", "fixture_path": str(root / "jira/epic_changelog.json")}
    )
    yt = YouTrackAdapter(
        {"team_field": "Team", "fixture_path": str(root / "youtrack/feature_changelog.json")}
    )
    je = jira.fetch({}).epics[0]
    ye = yt.fetch({}).epics[0]
    assert set(je.model_dump()) == set(ye.model_dump())
    assert je.team_id == ye.team_id == "alpha"
    children = jira.fetch({}).children
    assert all(c.external_id != je.external_id for c in children)
    assert all(c.external_id != "PROJ-1" or c.epic_external_id == "PROJ-1" for c in children)
    epic_ids = {e.external_id for e in jira.fetch({}).epics}
    assert "PROJ-2" not in epic_ids
