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
    """Forbid extra fields; strip surrounding whitespace on strings."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Epic(_Strict):
    """Canonical prediction unit. Children are never Epic rows."""

    tracker: str = Field(description="Tracker id such as jira, youtrack, or mock.")
    external_id: str = Field(description="Tracker id of the epic or feature.")
    team_id: str = Field(description="Team identity from the adapter field map only.")
    status: EpicStatus = Field(description="open, done, or cancelled.")
    committed_deadline: datetime | None = Field(
        default=None,
        description="First changelog due date, else current due.",
    )
    deadline_source: DeadlineSource | None = Field(
        default=None,
        description="changelog if history supplied the due date, else current_fallback.",
    )
    actual_completed_at: datetime | None = Field(
        default=None,
        description="Completion timestamp after applying epic_done. Null means open.",
    )
    created_at: datetime = Field(description="Epic creation time, UTC.")
    updated_at: datetime = Field(description="Last tracker update time, UTC.")
    title: str | None = Field(default=None, description="Optional summary.")
    estimate: float | None = Field(default=None, description="Optional epic-level size.")
    labels: list[str] = Field(default_factory=list, description="Optional tracker labels.")
    raw_payload_hash: str | None = Field(
        default=None,
        description="Short digest of the raw tracker payload for re-ingest change detection.",
    )


class ChildIssue(_Strict):
    """Non-predicted record under an epic, used for factors and completion fallback."""

    tracker: str = Field(description="Tracker id of the child issue.")
    external_id: str = Field(description="Tracker id of the child issue.")
    epic_external_id: str = Field(description="Parent epic external id.")
    status: str = Field(description="Tracker status of the child.")
    updated_at: datetime = Field(description="Last update time, UTC.")
    team_id: str | None = Field(
        default=None,
        description="May differ from the epic team (cross-team child).",
    )
    estimate: float | None = Field(default=None, description="Optional size for rollup features.")
    actual_completed_at: datetime | None = Field(
        default=None,
        description="Child completion, used by epic_done children / own_then_children.",
    )


class Dependency(_Strict):
    """Directed blocker link on an epic or child; the factor aggregates foreign team_id."""

    tracker: str = Field(description="Tracker id of the link.")
    from_external_id: str = Field(description="Blocked epic or child id.")
    to_external_id: str = Field(description="Blocker id.")
    from_kind: LinkKind = Field(description="Whether the blocked item is an epic or a child.")
    link_type: str = Field(default="blocks", description="Tracker link type.")
    to_team_id: str | None = Field(
        default=None, description="Foreign team of the blocker, if known."
    )


class Team(_Strict):
    """Deadline-setting group. No person entity and no inferred org chart."""

    team_id: str = Field(description="Primary key; created on ingest.")
    display_name: str | None = Field(default=None, description="Optional display label.")
    min_history: int | None = Field(
        default=None,
        description="Optional per-team override of the global cold-start threshold.",
    )
    active: bool = Field(default=True, description="Whether the team is included in training.")


class Slip(_Strict):
    """Signed lateness of a completed epic: actual completion minus committed deadline."""

    tracker: str = Field(description="Tracker of the epic.")
    external_id: str = Field(description="Epic external id.")
    unit: SlipUnit = Field(description="working_days (default) or calendar_days.")
    value: float = Field(description="Positive is late; negative is early.")


class TeamVacation(_Strict):
    """Team-level vacation interval. Person calendars are out of v1."""

    team_id: str = Field(description="Team this interval applies to.")
    start: datetime = Field(description="Inclusive start.")
    end: datetime = Field(description="Inclusive end.")
    capacity_factor: float = Field(
        default=0.0,
        description="0 means fully off; 1 means full capacity.",
    )


class CapacityCalendarConfig(_Strict):
    """Timezone, weekend, optional holidays, and team vacation intervals."""

    timezone: str = Field(default="UTC", description="IANA timezone name.")
    weekend: list[int] = Field(
        default_factory=lambda: [5, 6],
        description="Weekday numbers treated as weekend (Monday=0).",
    )
    holidays: list[datetime] = Field(
        default_factory=list, description="Org-wide non-working dates."
    )
    vacations: list[TeamVacation] = Field(
        default_factory=list,
        description="Team vacation intervals for the capacity factor.",
    )


class FactorSpec(_Strict):
    """Named factor in config: enable flag, version, and parameters."""

    name: str = Field(description="Registry name such as team_bias.")
    enabled: bool = Field(default=True, description="Disabled factors are omitted from the matrix.")
    version: str = Field(default="1", description="Included in factor_set_hash.")
    params: dict[str, Any] = Field(default_factory=dict, description="Factor-specific parameters.")


class ModelArtifact(_Strict):
    """Serialized backend plus factor hash and training metadata. At most one is_active."""

    id: UUID = Field(description="Artifact id.")
    backend: str = Field(description="Registry name of the learning backend.")
    backend_version: str = Field(description="Backend implementation version.")
    factor_set_hash: str = Field(description="Hash of enabled factor names, versions, and params.")
    quantiles: list[float] = Field(description="Quantile levels stored with the artifact.")
    slip_unit: SlipUnit = Field(description="Slip unit used at train time.")
    train_epic_count: int = Field(description="Completed epics in the training set.")
    train_team_count: int = Field(description="Distinct teams in the training set.")
    data_cutoff: datetime | None = Field(
        description="Max actual_completed_at among training epics.",
    )
    created_at: datetime = Field(description="When the artifact was stored.")
    blob_path: str = Field(description="Directory of the serialized model files.")
    min_history: int = Field(
        default=DEFAULT_MIN_HISTORY,
        description="Cold-start threshold pinned at train time.",
    )
    is_active: bool = Field(
        default=False,
        description="Last successful train sets this; predict uses the active artifact.",
    )


class PredictabilityResult(_Strict):
    """One epic prediction. Must not include person ids, slip, or ranks."""

    tracker: str = Field(description="Tracker of the scored epic.")
    external_id: str = Field(description="Epic external id.")
    team_id: str = Field(description="Team the epic belongs to.")
    committed_deadline: datetime = Field(description="Deadline used for on-time probability.")
    deadline_source: DeadlineSource = Field(description="How committed_deadline was chosen.")
    expected_slip: float = Field(description="Point estimate, typically the p50 quantile.")
    quantiles: dict[str, float] = Field(description="Map of quantile label to predicted slip.")
    on_time_probability: float = Field(
        description=(
            "P(slip <= 0). empirical_bayes uses a Gaussian CDF; "
            "quantile GBM extras use a logistic of p50 (not a calibrated CDF)."
        ),
    )
    cold_start: bool = Field(
        description="True when team_history_n is below the artifact min_history.",
    )
    team_history_n: int = Field(description="Completed training epics for this team.")
    model_id: str = Field(description="Artifact id used for this prediction.")
    backend: str = Field(description="Backend name on the artifact.")
    factor_set_hash: str = Field(description="Factor hash the artifact was trained with.")


class EvaluationRow(_Strict):
    """Walk-forward metrics for one backend. artifact_id stays null in v1."""

    backend: str = Field(description="Registry name evaluated.")
    mae_slip: float | None = Field(default=None, description="MAE of expected slip vs actual.")
    pinball: dict[str, float] = Field(
        default_factory=dict,
        description="Pinball loss per quantile label, e.g. 0.5 and 0.9.",
    )
    coverage_p50_p90: float | None = Field(
        default=None,
        description="Fraction of actual slip inside [p50, p90].",
    )
    brier_on_time: float | None = Field(
        default=None,
        description="Brier score of on-time probability.",
    )
    n_eval: int = Field(default=0, description="Number of scored future epics.")
    artifact_id: str | None = Field(
        default=None,
        description="Always null: evaluate does not use the serving artifact.",
    )
    error: str | None = Field(
        default=None,
        description="If set, this backend failed (e.g. missing extra) and metrics are empty.",
    )


class EvaluationReport(_Strict):
    """Walk-forward comparison across backends. Independent of is_active."""

    id: str = Field(description="Report id.")
    created_at: datetime = Field(description="When the report was produced.")
    split: dict[str, Any] = Field(description="Walk-forward split parameters.")
    dataset_cutoff: datetime | None = Field(
        default=None,
        description="Latest actual_completed_at in the evaluated history.",
    )
    rows: list[EvaluationRow] = Field(default_factory=list, description="One row per backend.")


class IngestReport(_Strict):
    """Counts from one ingest run. Upsert identity is (tracker, external_id)."""

    imported: int = Field(default=0, description="New epic rows inserted.")
    updated: int = Field(default=0, description="Existing epic rows updated.")
    children_imported: int = Field(default=0, description="New child rows inserted.")
    skipped_no_deadline: int = Field(
        default=0,
        description="Epics dropped because no deadline existed even as current due.",
    )
    skipped_unmapped_team: int = Field(
        default=0,
        description="Epics dropped because team_id was empty.",
    )
    deadline_changelog: int = Field(
        default=0,
        description="Accepted epics whose deadline came from changelog.",
    )
    deadline_fallback: int = Field(
        default=0,
        description="Accepted epics whose deadline was the current due date.",
    )
    invalid: int = Field(
        default=0, description="Rows rejected as invalid (e.g. completed before created)."
    )
    errors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Sample of skip/invalid reasons with external_id.",
    )
