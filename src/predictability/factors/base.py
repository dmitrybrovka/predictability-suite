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
    calendar: CapacityCalendar | None = None
    children: Sequence[ChildIssue] = field(default_factory=list)
    dependencies: Sequence[Dependency] = field(default_factory=list)
    as_of: datetime | None = None
    vacations: list[tuple[str, datetime, datetime, float]] = field(default_factory=list)
    # Slip-derived features must use the same unit as the training labels.
    slip_unit: SlipUnit = "working_days"


class Factor(Protocol):
    name: str
    version: str

    def fit(self, epics: Sequence[Epic], ctx: FactorContext) -> Factor: ...

    def transform(self, epics: Sequence[Epic], ctx: FactorContext) -> FeatureFrame: ...
