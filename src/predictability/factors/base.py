"""Factor protocol."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import pandas as pd

from predictability.core.calendar import CapacityCalendar
from predictability.core.schema import ChildIssue, Dependency, Epic, SlipUnit

FeatureFrame = pd.DataFrame


@dataclass
class FactorContext:
    """Shared context for factor fit/transform.

    Attributes:
        calendar: Weekend/holiday calendar. Vacations are listed separately.
        children: Child issues for size and dependency rollup.
        dependencies: Directed links on epics or children.
        as_of: Optional scoring time for capacity windows.
        vacations: Team intervals ``(team_id, start, end, capacity_factor)``.
        slip_unit: Must match training labels for slip-derived features.
    """

    calendar: CapacityCalendar | None = None
    children: Sequence[ChildIssue] = field(default_factory=list)
    dependencies: Sequence[Dependency] = field(default_factory=list)
    as_of: datetime | None = None
    vacations: list[tuple[str, datetime, datetime, float]] = field(default_factory=list)
    slip_unit: SlipUnit = "working_days"


class Factor(Protocol):
    """Named transform from epics plus context into a feature frame."""

    name: str
    version: str

    def fit(self, epics: Sequence[Epic], ctx: FactorContext) -> Factor:
        """Learn any state from ``epics`` (typically completed history)."""
        ...

    def transform(self, epics: Sequence[Epic], ctx: FactorContext) -> FeatureFrame:
        """Return one row per epic, indexed by ``tracker:external_id``."""
        ...
