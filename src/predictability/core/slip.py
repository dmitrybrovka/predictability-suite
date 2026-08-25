"""Slip = actual completion minus committed deadline."""

from __future__ import annotations

from predictability.core.calendar import CapacityCalendar
from predictability.core.errors import UsageError
from predictability.core.schema import Epic, Slip, SlipUnit


def compute_slip(
    epic: Epic,
    *,
    unit: SlipUnit = "working_days",
    calendar: CapacityCalendar | None = None,
) -> Slip:
    if epic.actual_completed_at is None or epic.committed_deadline is None:
        msg = "slip requires committed_deadline and actual_completed_at"
        raise UsageError(msg)
    cal = calendar or CapacityCalendar()
    if unit == "working_days":
        value = cal.signed_working_days(epic.committed_deadline, epic.actual_completed_at)
    elif unit == "calendar_days":
        value = cal.signed_calendar_days(epic.committed_deadline, epic.actual_completed_at)
    else:
        msg = f"unknown slip unit: {unit}"
        raise UsageError(msg)
    return Slip(
        tracker=epic.tracker,
        external_id=epic.external_id,
        unit=unit,
        value=value,
    )
