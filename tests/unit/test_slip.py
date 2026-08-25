from datetime import UTC, datetime

from predictability.core.calendar import CapacityCalendar
from predictability.core.slip import compute_slip
from predictability.core.synthetic import make_epic


def test_calendar_days_signed() -> None:
    epic = make_epic(
        external_id="E",
        team_id="t",
        slip_days=0,
        deadline=datetime(2026, 1, 1, tzinfo=UTC),
    )
    epic = epic.model_copy(update={"actual_completed_at": datetime(2026, 1, 4, tzinfo=UTC)})
    slip = compute_slip(epic, unit="calendar_days")
    assert slip.value == 3.0


def test_working_days_skip_weekend() -> None:
    # Friday to Monday = 1 working day (Monday counted, Sat/Sun skipped)
    start = datetime(2026, 1, 2, tzinfo=UTC)  # Friday
    end = datetime(2026, 1, 5, tzinfo=UTC)  # Monday
    cal = CapacityCalendar(weekend=(5, 6))
    assert cal.signed_working_days(start, end) == 1.0


def test_holidays_excluded_from_working_days() -> None:
    cal = CapacityCalendar(weekend=(5, 6), holidays=[datetime(2026, 1, 1, tzinfo=UTC).date()])
    start = datetime(2025, 12, 31, tzinfo=UTC)  # Wednesday
    end = datetime(2026, 1, 2, tzinfo=UTC)  # Friday
    # Thu Jan 1 holiday skipped, Fri Jan 2 counted
    assert cal.signed_working_days(start, end) == 1.0


def test_negative_slip_when_early() -> None:
    epic = make_epic(external_id="E", team_id="t", slip_days=-2)
    slip = compute_slip(epic, unit="calendar_days")
    assert slip.value == -2.0


def test_vacations_do_not_change_slip_definition() -> None:
    cal = CapacityCalendar()
    epic = make_epic(external_id="E", team_id="t", slip_days=5)
    a = compute_slip(epic, unit="calendar_days", calendar=cal)
    b = compute_slip(epic, unit="calendar_days", calendar=CapacityCalendar())
    assert a.value == b.value
