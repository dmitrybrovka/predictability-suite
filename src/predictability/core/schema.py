"""Canonical Pydantic v2 models. Public types MUST NOT include person fields."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MIN_HISTORY = 20

DeadlineSource = Literal["changelog", "current_fallback"]
EpicStatus = Literal["open", "done", "cancelled"]
SlipUnit = Literal["working_days", "calendar_days"]
LinkKind = Literal["epic", "child"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Epic(_Strict):
    tracker: str
    external_id: str
    team_id: str
    status: EpicStatus
    committed_deadline: datetime | None = None
    deadline_source: DeadlineSource | None = None
    actual_completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    estimate: float | None = None
    labels: list[str] = Field(default_factory=list)
    raw_payload_hash: str | None = None


class ChildIssue(_Strict):
    tracker: str
    external_id: str
    epic_external_id: str
    status: str
    updated_at: datetime
    team_id: str | None = None
    estimate: float | None = None
    actual_completed_at: datetime | None = None


class Dependency(_Strict):
    tracker: str
    from_external_id: str
    to_external_id: str
    from_kind: LinkKind
    link_type: str = "blocks"
    to_team_id: str | None = None


class Team(_Strict):
    team_id: str
    display_name: str | None = None
    min_history: int | None = None
    active: bool = True


class Slip(_Strict):
    tracker: str
    external_id: str
    unit: SlipUnit
    value: float


class TeamVacation(_Strict):
    team_id: str
    start: datetime
    end: datetime
    capacity_factor: float = 0.0


class CapacityCalendarConfig(_Strict):
    timezone: str = "UTC"
    weekend: list[int] = Field(default_factory=lambda: [5, 6])
    holidays: list[datetime] = Field(default_factory=list)
    vacations: list[TeamVacation] = Field(default_factory=list)


class FactorSpec(_Strict):
    name: str
    enabled: bool = True
    version: str = "1"
    params: dict[str, Any] = Field(default_factory=dict)


class ModelArtifact(_Strict):
    id: UUID
    backend: str
    backend_version: str
    factor_set_hash: str
    quantiles: list[float]
    slip_unit: SlipUnit
    train_epic_count: int
    train_team_count: int
    data_cutoff: datetime | None
    created_at: datetime
    blob_path: str
    # Cold-start threshold in force at train time. Pinned here so a later config
    # edit cannot silently reinterpret an existing artifact's cold_start flags.
    min_history: int = DEFAULT_MIN_HISTORY
    is_active: bool = False


class PredictabilityResult(_Strict):
    tracker: str
    external_id: str
    team_id: str
    committed_deadline: datetime
    deadline_source: DeadlineSource
    expected_slip: float
    quantiles: dict[str, float]
    on_time_probability: float
    cold_start: bool
    team_history_n: int
    model_id: str
    backend: str
    factor_set_hash: str


class EvaluationRow(_Strict):
    backend: str
    mae_slip: float | None = None
    pinball: dict[str, float] = Field(default_factory=dict)
    coverage_p50_p90: float | None = None
    brier_on_time: float | None = None
    n_eval: int = 0
    artifact_id: str | None = None
    error: str | None = None


class EvaluationReport(_Strict):
    id: str
    created_at: datetime
    split: dict[str, Any]
    dataset_cutoff: datetime | None = None
    rows: list[EvaluationRow] = Field(default_factory=list)


class IngestReport(_Strict):
    imported: int = 0
    updated: int = 0
    children_imported: int = 0
    skipped_no_deadline: int = 0
    skipped_unmapped_team: int = 0
    deadline_changelog: int = 0
    deadline_fallback: int = 0
    invalid: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)
