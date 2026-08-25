from datetime import UTC, datetime

from predictability.core.synthetic import make_epic
from predictability.factors.base import FactorContext
from predictability.factors.team_bias import TeamBiasFactor


def test_factor_rows_align_to_epics_and_no_leakage() -> None:
    early = make_epic(
        external_id="A", team_id="t", slip_days=10, created=datetime(2025, 1, 1, tzinfo=UTC)
    )
    later = make_epic(
        external_id="B", team_id="t", slip_days=0, created=datetime(2025, 6, 1, tzinfo=UTC)
    )
    # B's deadline is later; A completed before B's deadline
    factor = TeamBiasFactor()
    ctx = FactorContext()
    factor.fit([early, later], ctx)
    frame = factor.transform([later], ctx)
    team_n: object = frame.loc["mock:B", "team_n"]
    assert team_n == 1
    # later epic must not leak into earlier
    frame_early = factor.transform([early], ctx)
    assert frame_early.loc["mock:A", "team_n"] == 0
