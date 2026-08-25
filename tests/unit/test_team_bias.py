from datetime import UTC, datetime

from predictability.core.synthetic import make_epic
from predictability.factors.base import FactorContext
from predictability.factors.team_bias import TeamBiasFactor


def test_team_bias_uses_only_prior_completions() -> None:
    a = make_epic(
        external_id="A", team_id="t", slip_days=9, created=datetime(2025, 1, 1, tzinfo=UTC)
    )
    b = make_epic(
        external_id="B", team_id="t", slip_days=1, created=datetime(2025, 3, 1, tzinfo=UTC)
    )
    factor = TeamBiasFactor()
    factor.fit([a, b], FactorContext())
    fa = factor.transform([a], FactorContext())
    fb = factor.transform([b], FactorContext())
    assert fa.loc["mock:A", "team_n"] == 0
    assert fb.loc["mock:B", "team_n"] == 1
    mean: object = fb.loc["mock:B", "team_mean_slip"]
    assert isinstance(mean, int | float)
    assert mean > 0


def test_team_bias_honours_context_slip_unit() -> None:
    """The feature must use the unit the labels were built with, or the model sees
    working-day features against calendar-day targets."""
    done = make_epic(
        external_id="A", team_id="t", slip_days=7, created=datetime(2025, 1, 1, tzinfo=UTC)
    )
    later = make_epic(
        external_id="B", team_id="t", slip_days=0, created=datetime(2025, 6, 1, tzinfo=UTC)
    )
    working = FactorContext(slip_unit="working_days")
    calendar = FactorContext(slip_unit="calendar_days")
    working_mean = TeamBiasFactor().fit([done], working).transform([later], working)
    calendar_mean = TeamBiasFactor().fit([done], calendar).transform([later], calendar)
    working_value: object = working_mean.loc["mock:B", "team_mean_slip"]
    calendar_value: object = calendar_mean.loc["mock:B", "team_mean_slip"]
    assert working_value == 5.0
    assert calendar_value == 7.0
