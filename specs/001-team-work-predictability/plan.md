# Implementation Plan: Team Work Predictability Suite

**Branch**: `001-team-work-predictability` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-team-work-predictability/spec.md`

**Note**: Updated after grill-me (2026-08-24). HTTP/requirement 5 is **v2**.

## Summary

Build an MIT-licensed Python **library + CLI** that estimates Team Work Predictability from **epic-level deadline slip** (first changelog due date vs actual completion). v1 includes a SQLite store, pluggable factors (`team_bias`, team vacations, cross-team deps with child rollup), Jira/YouTrack/mock adapters (changelog required), and a model registry: **`empirical_bayes`** (bias baseline) plus **`quantile_catboost`** and **`quantile_lightgbm`**. `train` refits from stored history and becomes the active artifact for `predict`. `evaluate` is **walk-forward only** and does not call that artifact. Intranet HTTP is deferred to v2.

Variants: [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.11+ (develop/CI on 3.12; existing `.venv` is 3.12.13)

**Primary Dependencies**: pydantic v2, pandas, SQLAlchemy 2, PyYAML, httpx (adapters); extras `[catboost]`, `[gbm]` (LightGBM)

**Storage**: SQLite file via SQLAlchemy 2 (`--db`, default `./predictability.sqlite`)

**Testing**: pytest; contract tests for adapter/factor/model/CLI; tracker **fixtures including changelog** (no live network in default CI); walk-forward fixture (≥1,000 completed **epics**)

**Target Platform**: Linux/macOS laptops and internal job runners; air-gapped after install; no v1 container product

**Project Type**: library + CLI (HTTP extra is v2)

**Performance Goals**: full refit of 10k completed epics (plus children) in < 10 minutes on a 4-core laptop; CLI `predict` of 100 open epics with a loaded CatBoost artifact in < 5 seconds process time after import

**Constraints**: no HTTP server, Redis, Kafka, cloud, or SSO in v1; no person-level scores; slip in UTC-normalized dates; working-day default; MIT

**Scale/Scope**: one org per DB file; tens of teams; 10³–10⁴ historical epics; three built-in factors; three backends; two tracker adapters + mock

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.0.0 (ratified 2026-08-24).

| Principle | How this plan complies |
|-----------|------------------------|
| I. Library-First | `src/predictability/` importable; no FastAPI in v1 |
| II. CLI Interface | `ingest`, `train`, `predict`, `evaluate` — no `serve` |
| III. Test-First | Protocol + walk-forward fixtures before implement; pytest + 90% coverage |
| IV. Contract tests | CLI + adapter/factor/model protocols; OpenAPI filed as v2 |
| V. Quality Gates | Ruff lint/format, mypy strict, pytest, pre-commit; no second formatter |
| VI. Simplicity | SQLite, full refit, epic grain, HTTP deferred |

**Gate status (pre-research)**: PASS WITH NOTE (constitution was still a template).

**Gate status (post-design / post-grill / post-ratification)**: PASS. v1 is simpler than the first draft (no HTTP). Three model names are required by FR-011 (bias + two GBM libraries). Complexity Tracking records that dual-GBM exception.

## Project Structure

### Documentation (this feature)

```text
specs/001-team-work-predictability/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md                 # v1 public surface
│   ├── adapter-protocol.md
│   ├── factor-protocol.md
│   ├── model-protocol.md
│   └── openapi.yaml           # v2 deferred (requirement 5)
└── tasks.md                   # /speckit-tasks — not created here
```

### Source Code (repository root)

```text
src/predictability/
├── __init__.py
├── py.typed
├── cli.py
├── __main__.py
├── core/                    # Epic, ChildIssue, slip, calendar, config, score, registry
├── adapters/                # base, mock, jira, youtrack (changelog)
├── factors/                 # team_bias, capacity_calendar, cross_team_deps, pipeline
├── models/                  # empirical_bayes, quantile_catboost, quantile_lightgbm
├── training/                # full refit + cold_start meta
├── evaluation/              # walk-forward only
└── store/                   # sqlite + artifacts

tests/
├── contract/
├── integration/
└── unit/

config/
├── default.yaml
├── example_vacations.yaml   # team intervals
└── example_holidays.yaml

pyproject.toml
```

**Structure Decision**: Single src-layout package. No `api/` package, Dockerfile, or compose in **v1**. Add them in the v2 feature for requirement 5.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Two GBM libraries | User required comparing libraries (FR-011); CatBoost requested explicitly | One GBM hides requirement 4; wrapping both in one class hides the swap |
