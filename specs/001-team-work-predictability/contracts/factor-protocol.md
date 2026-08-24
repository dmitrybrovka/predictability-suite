# Factor protocol

**Feature**: `001-team-work-predictability`  
**Consumers**: training, walk-forward evaluate, plugins

## Purpose

Turn **epics** + children + calendars + graphs into a feature matrix. Backends do not hard-code factor names.

`team_bias` is **default-enabled** so GBM models still see explicit bias features; `empirical_bayes` also encodes bias as the model itself (FR-019).

## Registration

Entry point group: `predictability.factors`

Built-ins: `team_bias`, `capacity_calendar`, `cross_team_deps`.

## Interface

```python
class FactorContext:
    calendar: CapacityCalendar | None
    children: Sequence[ChildIssue]
    dependencies: Sequence[Dependency]
    as_of: datetime

class Factor(Protocol):
    name: str
    version: str

    def fit(self, epics: Sequence[Epic], ctx: FactorContext) -> Self: ...
    def transform(self, epics: Sequence[Epic], ctx: FactorContext) -> FeatureFrame: ...
```

Rows of `FeatureFrame` align to **epic** ids only.

## Built-in semantics

| Factor | Fit | Transform |
|--------|-----|-----------|
| `team_bias` | per-team mean/std/n of **epic** slip (completed only, no leakage) | `team_n`, `team_mean_slip`, `team_std_slip`, `global_mean_slip`, `shrinkage_w` |
| `capacity_calendar` | holiday file hash optional | `vacation_overlap_days`, `holiday_overlap_days` on `[as_of, deadline]` using **team** vacations |
| `cross_team_deps` | optional | `foreign_team_blocker_count` from epic links ∪ child links, **deduped by `team_id`**; optional `dep_depth` |

Child-derived columns (from `ctx.children`, not separate factors unless split later): e.g. `child_count`, `open_child_count`, `child_estimate_sum`, `foreign_child_team_count`.

## Leakage

- Train-time features use knowledge available at `as_of` ≤ `committed_deadline`.
- `team_bias` for epic i uses only slips with `actual_completed_at` **strictly before** i’s `committed_deadline`.
- Walk-forward **re-fits** factors at each origin.

## Config example

```yaml
factors:
  - name: team_bias
    enabled: true
    params: { shrinkage_k: 10, min_history: 20 }
  - name: capacity_calendar
    enabled: true
    params:
      vacations_path: config/example_vacations.yaml
      holidays_path: config/example_holidays.yaml
      timezone: Europe/Moscow
  - name: cross_team_deps
    enabled: true
    params: { max_depth: 4 }
```
