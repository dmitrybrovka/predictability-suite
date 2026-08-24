# Research: Team Work Predictability Suite

**Feature**: `001-team-work-predictability`  
**Date**: 2026-08-24  
**Updated**: 2026-08-24 (grill-me decisions)

Chosen designs plus rejected alternatives. Grill-me answers override the first draft where they conflict.

---

## R1. Overall product shape

### Decision

v1: **one Python library** (`predictability`) with **library API + CLI** (`ingest`, `train`, `predict`, `evaluate`). Persistence: **SQLite** (`--db`).

**Requirement 5 (HTTP / FastAPI / OpenAPI / `serve`) is v2**, not a v1 extra.

### Rationale

User chose library-first and explicitly postponed requirement 5. SQLite still supports upsert, refit, and open-epic `predict` without a process daemon.

### Alternatives considered

| Option | Verdict | Why not |
|--------|---------|---------|
| Library + CLI + HTTP in one v1 release | Rejected for v1 | User: HTTP in v2 |
| HTTP as the primary surface | Rejected | User: library/CLI first |
| Microservices | Rejected | Ops cost |
| No store (caller passes full dataset every train) | Rejected | Breaks requirement 3 |
| Postgres-only | Rejected for v1 | Extra ops for CLI |

---

## R2. Predictability target and grain

### Decision

**Unit of prediction = epic/feature** (configured issue types), not child issues and not people.

`slip = date(actual_completed_at) − date(committed_deadline)`  
Default unit: **working days** (weekend + optional holidays + timezone); calendar days via config.

Outputs: expected slip, **p50/p90**, **P(slip ≤ 0)**, model identity, `cold_start`.

**Deadline**: first non-null due date in **changelog**, else current due + `deadline_source=current_fallback`.

**Completion**: adapter `epic_done`: `own | children | own_then_children`, default **`own_then_children`**.

**Train**: completed epics only. **Predict**: open epics (file and/or store). No survival in v1.

### Rationale

User chose epic grain and original-commitment semantics. Sliding last due date would reward moving dates. Children-as-target would split the unit.

### Alternatives considered

| Option | Verdict | Why not |
|--------|---------|---------|
| Issue-level prediction | Rejected | User: epic/feature |
| Sprint as atom | Rejected | Not in tracker as the due-date entity |
| Last/current due date only | Rejected | User: first changelog date |
| Configurable first_set \| last_set \| custom as the *only* product rule | Rejected | User locked **B** (changelog first) |
| Survival on open items | Deferred | User: completed-only train |
| Person scores | Forbidden | User: never in public API |

---

## R3. Requirement 1 — factors

### Decision

Plugin factors. Built-ins:

- `team_bias` — per-team mean/std/n + shrinkage; **default on for GBM**; also the core of `empirical_bayes`
- `capacity_calendar` — **team** vacation YAML + org holidays/weekends (no person calendar in v1)
- `cross_team_deps` — epic links **union** child-link rollup, **dedupe by `team_id`**

Children of an epic are **feature sources** (counts, remaining, foreign teams), not rows in `predict`.

### Rationale

User: keep bias first-class; team vacations only; deps otherwise empty on typical Jira epics.

### Alternatives considered

| Option | Verdict | Why not |
|--------|---------|---------|
| Vacations per person aggregated in v1 | Deferred | User: team YAML |
| Tempo/tracker absences in v1 | Deferred | Vendor lock-in |
| Skip vacation factor in v1 | Rejected | Requirement 1 |
| Predict children and epics (two grains) | Rejected | User: children = factors only |
| Epic links only | Rejected | User: A+B rollup |

---

## R4. Requirement 2 — adapters

### Decision

Canonical **Epic** + **ChildIssue**. Entry points `predictability.adapters`.

`team_id` and epic types come from **adapter config** (no inference).

Jira **and** YouTrack in v1; **changelog is mandatory** for both; CI uses fixtures (including changelog). Live API optional.

If changelog cannot be read: **do not fail ingest**; use current due + flag (per-item). Whole-run fail only on auth/config/hard errors.

`epic_done` configurable; default `own_then_children`.

### Alternatives considered

| Option | Verdict | Why not |
|--------|---------|---------|
| Changelog required or item dropped | Rejected | User: fallback + flag |
| YouTrack without changelog until v1.1 | Rejected | Two slip semantics |
| Mock-only ingest in v1 | Rejected | User: both adapters |
| Infer team from assignee/component | Rejected | User: explicit map |

---

## R5. Requirement 3 — continued training

### Decision

Store is source of truth. **Full refit** from all completed epics. New teams: shrinkage `w = n/(n+k)`, `cold_start` while `n < min_history`. Predict never errors solely because the team is new.

### Alternatives considered

| Option | Verdict | Why not |
|--------|---------|---------|
| Online `partial_fit` only | Rejected | User: full refit |
| One model file per team, error on new team | Rejected | User: cold start |
| Refit only teams in the latest batch | Rejected | Global bias/GBM need full frame |

---

## R6. Requirement 4 — compare and swap libraries

### Decision

Protocol: `fit`, `predict_quantiles`, `predict_on_time_proba`, `save`/`load`.

v1 registry:

| Name | Extra | Role |
|------|-------|------|
| `empirical_bayes` | core | Interpretable **bias** baseline |
| `quantile_catboost` | `[catboost]` | GBM |
| `quantile_lightgbm` | `[gbm]` | GBM |

**Not** one `quantile_gbm` class with a library switch — two names so `evaluate` compares libraries.

**`evaluate`**: walk-forward only (re-fit each origin). **Does not** load or change the serving artifact. User confirmed “leave as is” (not `evaluate --artifact`).

**`predict`**: last successful `train` (activate by default). Inputs: canonical file **or** `--status open` from store.

Swap: read `evaluate` report → `train --backend <winner>` (new active artifact).

### Alternatives considered

| Option | Verdict | Why not |
|--------|---------|---------|
| LightGBM only | Rejected | User asked to include CatBoost |
| CatBoost only | Rejected | User: both registry names |
| Single wrapper `gbm.library:` | Rejected | User: separate names |
| Drop empirical_bayes once GBMs exist | Rejected | User: do not forget bias |
| `evaluate` scores the current artifact | Rejected | User: leave walk-forward as designed |
| Auto-activate evaluate winner | Rejected | Too magical; train activates |

---

## R7. Requirement 5 — HTTP

### Decision

**Deferred to v2.** Draft OpenAPI remains in `contracts/openapi.yaml` as a future contract, not a v1 implementation target.

### Alternatives considered

| Option | Verdict | Why not v1 |
|--------|---------|------------|
| Thin FastAPI extra in v1 | Rejected | User postponed requirement 5 |
| Stub `serve` command | Rejected | Pulls FastAPI “for later” |

---

## R8. Language, packaging, testing

### Decision

Python 3.11+, `src/` layout, MIT. Core extras-free except adapter HTTP client. `[catboost]` and `[gbm]` optional. pytest; changelog fixtures.

### Alternatives considered

R / TypeScript — rejected (ecosystem). Poetry-only — unnecessary.

---

## R9. Constitution

Unratified template. Plan does not rewrite it.

---

## Clarifications resolved (including grill-me)

| Topic | Resolution |
|-------|------------|
| Grain | Epic/feature |
| Surfaces v1 | Library + CLI; HTTP v2 |
| Person scores | Forbidden in public API |
| Deadline | First changelog due date; else current + flag |
| Epic done | Config; default `own_then_children` |
| Children | Factors only |
| Slip unit | Config; default working days |
| Vacations | Team YAML |
| Deps | Epic links ∪ child rollup; dedupe team_id |
| Store | SQLite |
| Incremental | Full refit + cold_start |
| Backends | empirical_bayes + CatBoost + LightGBM |
| evaluate | Walk-forward only; not serving predict |
| predict sources | File and store |
| Active model | Last train |

No remaining **NEEDS CLARIFICATION** for v1 design.
