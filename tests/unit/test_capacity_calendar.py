from datetime import UTC, datetime
from pathlib import Path

from predictability.core.calendar import CapacityCalendar
from predictability.core.config import AppConfig
from predictability.core.slip import compute_slip
from predictability.core.synthetic import make_epic
from predictability.factors.base import FactorContext
from predictability.factors.capacity_calendar import CapacityCalendarFactor, calendar_from_config
from predictability.factors.pipeline import build_matrix


def test_vacation_overlap_counts_working_days_only(tmp_path: Path) -> None:
    vac = tmp_path / "v.yaml"
    vac.write_text(
        "vacations:\n  - team_id: t\n    start: 2026-01-02\n    end: 2026-01-06\n    capacity_factor: 0\n",
        encoding="utf-8",
    )
    factor = CapacityCalendarFactor({"vacations_path": str(vac)})
    epic = make_epic(
        external_id="E",
        team_id="t",
        slip_days=0,
        open_item=True,
        created=datetime(2026, 1, 1, tzinfo=UTC),
        deadline=datetime(2026, 1, 8, tzinfo=UTC),
    )
    ctx = FactorContext(calendar=CapacityCalendar(weekend=(5, 6)))
    factor.fit([epic], ctx)
    frame = factor.transform([epic], ctx)
    # Fri 2, Mon 5, Tue 6 (Sat 3 Sun 4 skipped) = 3 working vacation days
    assert frame.loc["mock:E", "vacation_overlap_days"] == 3.0


def test_holidays_survive_a_context_calendar_without_them(tmp_path: Path) -> None:
    hol = tmp_path / "h.yaml"
    hol.write_text("holidays:\n  - 2026-01-01\n", encoding="utf-8")
    factor = CapacityCalendarFactor({"holidays_path": str(hol)})
    epic = make_epic(
        external_id="E",
        team_id="t",
        slip_days=0,
        open_item=True,
        created=datetime(2025, 12, 31, tzinfo=UTC),
        deadline=datetime(2026, 1, 2, tzinfo=UTC),
    )
    ctx = FactorContext(calendar=CapacityCalendar(weekend=(5, 6)))
    factor.fit([epic], ctx)
    frame = factor.transform([epic], ctx)
    assert frame.loc["mock:E", "holiday_overlap_days"] == 1.0
    assert ctx.calendar is not None
    assert datetime(2026, 1, 1, tzinfo=UTC).date() in ctx.calendar.holidays


def test_calendar_from_config_feeds_slip_and_the_factor_matrix(tmp_path: Path) -> None:
    hol = tmp_path / "h.yaml"
    hol.write_text("holidays:\n  - 2026-01-01\n", encoding="utf-8")
    cfg = AppConfig(
        {
            "factors": [
                {
                    "name": "capacity_calendar",
                    "enabled": True,
                    "params": {"holidays_path": str(hol)},
                }
            ]
        }
    )
    cal = calendar_from_config(cfg)
    start = datetime(2025, 12, 31, tzinfo=UTC)
    end = datetime(2026, 1, 2, tzinfo=UTC)
    assert cal.signed_working_days(start, end) == 1.0
    epic = make_epic(
        external_id="E",
        team_id="t",
        slip_days=0,
        created=start,
        deadline=start,
    )
    epic = epic.model_copy(update={"actual_completed_at": end})
    assert compute_slip(epic, calendar=cal).value == 1.0

    open_e = make_epic(
        external_id="OPEN",
        team_id="t",
        slip_days=0,
        open_item=True,
        created=start,
        deadline=end,
    )
    matrix = build_matrix([open_e], config=cfg, ctx=FactorContext(calendar=cal))
    assert float(matrix.iloc[0]["holiday_overlap_days"]) == 1.0
