"""Working-day and calendar-day counting. Vacations do not affect slip."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime


def _as_date(value: datetime | date) -> date:
    if isinstance(value, datetime):
        return value.astimezone(UTC).date()
    return value


class CapacityCalendar:
    """Timezone + weekend + optional holidays. Vacations are a factor, not slip."""

    def __init__(
        self,
        *,
        timezone: str = "UTC",
        weekend: Iterable[int] | None = None,
        holidays: Iterable[date | datetime] | None = None,
    ) -> None:
        self.timezone = timezone
        self.weekend = set(weekend if weekend is not None else (5, 6))
        self.holidays = {_as_date(h) for h in (holidays or ())}

    def is_working_day(self, day: date) -> bool:
        if day.weekday() in self.weekend:
            return False
        return day not in self.holidays

    def signed_working_days(self, start: datetime | date, end: datetime | date) -> float:
        """Signed count of working days from start date to end date (end exclusive of start)."""
        a = _as_date(start)
        b = _as_date(end)
        if a == b:
            return 0.0
        step = 1 if b > a else -1
        current = a
        count = 0
        while current != b:
            current = date.fromordinal(current.toordinal() + step)
            if self.is_working_day(current):
                count += step
        return float(count)

    def signed_calendar_days(self, start: datetime | date, end: datetime | date) -> float:
        return float((_as_date(end) - _as_date(start)).days)
