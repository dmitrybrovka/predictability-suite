from datetime import UTC, datetime

from predictability.core.schema import ChildIssue, Dependency
from predictability.core.synthetic import make_epic
from predictability.factors.base import FactorContext
from predictability.factors.cross_team_deps import CrossTeamDepsFactor


def test_rollup_dedupe_and_cycle_depth() -> None:
    epic = make_epic(external_id="E", team_id="home", slip_days=0, open_item=True)
    child = ChildIssue(
        tracker="mock",
        external_id="C1",
        epic_external_id="E",
        team_id="home",
        status="open",
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    deps = [
        Dependency(
            tracker="mock",
            from_external_id="E",
            to_external_id="X",
            from_kind="epic",
            to_team_id="foreign",
        ),
        Dependency(
            tracker="mock",
            from_external_id="C1",
            to_external_id="Y",
            from_kind="child",
            to_team_id="foreign",
        ),
        Dependency(
            tracker="mock",
            from_external_id="X",
            to_external_id="E",
            from_kind="epic",
            to_team_id="home",
        ),
    ]
    factor = CrossTeamDepsFactor({"max_depth": 4})
    ctx = FactorContext(children=[child], dependencies=deps)
    frame = factor.transform([epic], ctx)
    assert frame.loc["mock:E", "foreign_team_blocker_count"] == 1.0
    assert frame.loc["mock:E", "child_count"] == 1.0
