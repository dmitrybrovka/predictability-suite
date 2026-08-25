"""Team vacation / holiday overlap on the committed window."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from predictability.core.calendar import CapacityCalendar, _as_date
from predictability.core.config import AppConfig
from predictability.core.schema import Epic
from predictability.factors.base import FactorContext, FeatureFrame


def load_vacations(path: Path | None) -> list[tuple[str, date, date, float]]:
    if path is None or not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = raw.get("vacations") or raw if isinstance(raw, dict) else raw
    out: list[tuple[str, date, date, float]] = []
    if isinstance(items, dict):
        items = items.get("vacations") or []
    for item in items or []:
        start = datetime.fromisoformat(str(item["start"])).date()
        end = datetime.fromisoformat(str(item["end"])).date()
        out.append((str(item["team_id"]), start, end, float(item.get("capacity_factor", 0.0))))
    return out


def load_holidays(path: Path | None) -> list[date]:
    if path is None or not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    days = raw.get("holidays") or []
    return [datetime.fromisoformat(str(d)).date() for d in days]


def calendar_from_config(cfg: AppConfig) -> CapacityCalendar:
    """Shared slip + factor calendar: timezone, weekend, and org holidays."""
    return CapacityCalendar(
        timezone=cfg.timezone,
        weekend=cfg.weekend,
        holidays=load_holidays(cfg.holidays_path),
    )


class CapacityCalendarFactor:
    name = "capacity_calendar"
    version = "1.0.0"

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        self.vacations_path = (
            Path(params["vacations_path"]) if params.get("vacations_path") else None
        )
        self.holidays_path = Path(params["holidays_path"]) if params.get("holidays_path") else None
        self.vacations = load_vacations(self.vacations_path)
        holidays = load_holidays(self.holidays_path)
        self.calendar = CapacityCalendar(
            timezone=str(params.get("timezone", "UTC")),
            holidays=holidays,
        )

    def fit(self, epics: Sequence[Epic], ctx: FactorContext) -> CapacityCalendarFactor:
        if ctx.vacations:
            self.vacations = [(t, _as_date(a), _as_date(b), f) for t, a, b, f in ctx.vacations]
        if ctx.calendar is not None:
            # A holiday-less context calendar used to wipe holidays loaded from
            # params. Merge so slip and the factor see the same set.
            ctx.calendar.holidays |= self.calendar.holidays
            self.calendar = ctx.calendar
        return self

    def transform(self, epics: Sequence[Epic], ctx: FactorContext) -> FeatureFrame:
        cal = ctx.calendar or self.calendar
        rows = []
        for epic in epics:
            vac = 0.0
            hol = 0.0
            if epic.committed_deadline is not None:
                as_of = (ctx.as_of or epic.created_at).astimezone(UTC).date()
                end = epic.committed_deadline.astimezone(UTC).date()
                start, stop = (as_of, end) if as_of <= end else (end, as_of)
                day = start
                while day <= stop:
                    on_vacation = any(
                        team == epic.team_id and a <= day <= b and cap < 1.0
                        for team, a, b, cap in self.vacations
                    )
                    if on_vacation and cal.is_working_day(day):
                        vac += 1.0
                    elif day in cal.holidays:
                        hol += 1.0
                    day = date.fromordinal(day.toordinal() + 1)
            rows.append(
                {
                    "epic_id": f"{epic.tracker}:{epic.external_id}",
                    "vacation_overlap_days": vac,
                    "holiday_overlap_days": hol,
                }
            )
        return pd.DataFrame(rows).set_index("epic_id")
