# Data Model: Team Work Predictability Suite

**Feature**: `001-team-work-predictability`  
**Date**: 2026-08-24  
**Related**: [spec.md](./spec.md), [research.md](./research.md)

Prediction grain is **Epic**. Child issues are supporting records.

---

## Epic

Canonical unit of train/predict.

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `tracker` | string | yes | `jira`, `youtrack`, `mock` |
| `external_id` | string | yes | Tracker id of the epic/feature |
| `team_id` | string | yes | From adapter field map |
| `title` | string | no | |
| `status` | string | yes | `open` \| `done` \| `cancelled` |
| `committed_deadline` | datetime (UTC) | yes for train/predict | First changelog due date or current due |
| `deadline_source` | string | yes | `changelog` \| `current_fallback` |
| `actual_completed_at` | datetime (UTC) \| null | no | Per `epic_done` rule; null ⇒ open |
| `created_at` / `updated_at` | datetime (UTC) | yes | |
| `estimate` | number \| null | no | Epic-level size if present |
| `labels` | string[] | no | |
| `raw_payload_hash` | string | no | |

**Identity**: unique `(tracker, external_id)`. Re-ingest **upserts**.

**Validation**:

- No `team_id` or no deadline even after fallback ⇒ skip (`skipped_unmapped_team` / `skipped_no_deadline`)
- `cancelled` ⇒ not in train
- `actual_completed_at` before `created_at` ⇒ invalid
- Child issues are **not** Epic rows

---

## ChildIssue

Not a prediction object.

| Field | Type | Notes |
|-------|------|--------|
| `tracker` | string | |
| `external_id` | string | |
| `epic_external_id` | string | Parent epic |
| `team_id` | string \| null | May differ from epic (cross-team) |
| `status` | string | |
| `estimate` | number \| null | |
| `actual_completed_at` | datetime \| null | For `epic_done=children` / fallback |
| `updated_at` | datetime | |

Used for: completion fallback, remaining/size features, dependency rollup.

---

## Slip

Derived for completed epics only.

| Field | Type | Notes |
|-------|------|--------|
| `epic_pk` | FK | |
| `unit` | `working_days` \| `calendar_days` | Config; default working days |
| `value` | float | completion − deadline; negative = early |

Working-day unit uses weekend + optional holidays. Team vacations affect the **capacity factor**, not the slip definition (unless a future config says otherwise).

---

## Team

| Field | Type | Notes |
|-------|------|--------|
| `team_id` | string | PK; created on ingest |
| `display_name` | string \| null | |
| `min_history` | int \| null | Override global |
| `active` | bool | default true |

No person entity. No org chart.

---

## Dependency

| Field | Type | Notes |
|-------|------|--------|
| `tracker` | string | |
| `from_external_id` | string | Blocked epic **or** child |
| `to_external_id` | string | Blocker |
| `from_kind` | `epic` \| `child` | |
| `link_type` | string | |
| `to_team_id` | string \| null | |

`cross_team_deps` unions epic-level and child-level links, then **dedupes by foreign `team_id`**. Cycles: max depth (default 4), warn, do not fail ingest.

---

## CapacityCalendar

| Field | Type | Notes |
|-------|------|--------|
| `timezone` | IANA string | default `UTC` |
| `weekend` | int[] | default Sat/Sun |
| `holidays` | date[] | optional org file |
| `vacations` | TeamVacation[] | **team only in v1** |

### TeamVacation

| Field | Type | Notes |
|-------|------|--------|
| `team_id` | string | |
| `start` / `end` | date | inclusive |
| `capacity_factor` | float | 0 = fully off; default 0 |

---

## FactorConfig / FactorState

| Field | Type | Notes |
|-------|------|--------|
| `name` | string | |
| `version` | string | |
| `enabled` | bool | `team_bias` default true |
| `params` | object | |
| `fitted_state` | JSON/blob | |

**Pipeline hash** (enabled names + versions + params) stored on `ModelArtifact`.

---

## ModelArtifact

| Field | Type | Notes |
|-------|------|--------|
| `id` | UUID | |
| `backend` | string | `empirical_bayes` \| `quantile_catboost` \| `quantile_lightgbm` \| plugin |
| `backend_version` | string | |
| `factor_set_hash` | string | |
| `quantiles` | float[] | default `[0.5, 0.9]` |
| `slip_unit` | string | |
| `train_epic_count` | int | |
| `train_team_count` | int | |
| `data_cutoff` | datetime | max `actual_completed_at` in train |
| `created_at` | datetime | |
| `blob_path` | string | |
| `is_active` | bool | last successful `train` sets this; at most one active |

`evaluate` **must not** write `is_active`.

---

## EvaluationReport

Walk-forward only. Not tied to the serving artifact.

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | |
| `created_at` | datetime | |
| `split` | object | `min_train`, horizon, origins |
| `dataset_cutoff` | datetime | |
| `rows` | EvaluationRow[] | one per backend compared |

### EvaluationRow

| Field | Type | Notes |
|-------|------|--------|
| `backend` | string | |
| `mae_slip` | float | |
| `pinball` | map quantile→float | |
| `coverage_p50_p90` | float | |
| `brier_on_time` | float | |
| `n_eval` | int | |
| `artifact_id` | null | v1: folds are ephemeral; not the serving id |

---

## PredictabilityResult

| Field | Type | Notes |
|-------|------|--------|
| `tracker`, `external_id`, `team_id` | string | epic ids |
| `committed_deadline` | datetime | |
| `deadline_source` | string | echo |
| `expected_slip` | float | |
| `quantiles` | map | `"0.5"`, `"0.9"` |
| `on_time_probability` | float | |
| `cold_start` | bool | |
| `team_history_n` | int | |
| `model_id` | string | **active** artifact |
| `backend` | string | |
| `factor_set_hash` | string | |

MUST NOT include person ids, person slip, or person ranks.

---

## IngestReport

| Field | Type | Notes |
|-------|------|--------|
| `imported` / `updated` | int | epics upserted |
| `children_imported` | int | |
| `skipped_no_deadline` | int | |
| `skipped_unmapped_team` | int | |
| `deadline_changelog` / `deadline_fallback` | int | |
| `invalid` | int | |
| `errors` | object[] | sample |

---

## Relationships

```text
Team 1 ──< Epic
Epic 1 ──< ChildIssue
Epic 1 ──< Dependency (from_kind=epic)
ChildIssue 1 ──< Dependency (from_kind=child)
Epic 1 ── 0..1 Slip
ModelArtifact (is_active) ── used by ── PredictabilityResult
EvaluationReport 1 ──< EvaluationRow     # no FK to active artifact
```

---

## State transitions

### Epic.status

```text
open → done | cancelled
done → open     # upsert if tracker reopened; slip removed
```

Train: `status=done` AND non-null `actual_completed_at`.

### ModelArtifact

```text
created by train → active (default)
previous active → archived
evaluate → no transition on artifacts
```
