---
description: "Task list for Team Work Predictability Suite v1"
---

# Tasks: Team Work Predictability Suite

**Input**: Design documents from `/specs/001-team-work-predictability/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: MANDATORY (constitution III). Write each story's tests first and confirm they FAIL before implementation.

**Organization**: Phases follow user stories US1–US6 from spec.md. HTTP/`serve`/OpenAPI runtime is **v2 — do not implement**.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no unfinished dependencies)
- **[Story]**: US1…US6 on user-story tasks only
- Paths are repository-root relative

Already done (do not redo): `pyproject.toml` (hatch, ruff, mypy, pytest, `[dev]`/`[catboost]`/`[gbm]` extras), `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `src/predictability/{__init__.py,py.typed}`, `tests/{unit,contract,integration}/`, constitution v1.0.0.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Remaining src-layout packages, CLI/plugin wiring, example config

- [X] T001 Create package directories with `__init__.py` at `src/predictability/core/`, `src/predictability/adapters/`, `src/predictability/factors/`, `src/predictability/models/`, `src/predictability/training/`, `src/predictability/evaluation/`, `src/predictability/store/`, and `config/`
- [X] T002 [P] Add `[project.scripts]` `predictability = "predictability.cli:main"` and empty entry-point groups `predictability.adapters`, `predictability.factors`, `predictability.models` in `pyproject.toml`
- [X] T003 [P] Write `config/default.yaml`, `config/example_vacations.yaml`, and `config/example_holidays.yaml` matching [factor-protocol.md](./contracts/factor-protocol.md) config example
- [X] T004 [P] Verify quality gates still pass via `pre-commit run --all-files` using `.pre-commit-config.yaml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Canonical types, slip calendar, config, SQLite store, errors, plugin registry

**⚠️ CRITICAL**: No user story work until this phase is complete

- [X] T005 [P] Write failing unit tests for Epic, ChildIssue, Dependency, Team, Slip, IngestReport, ModelArtifact, PredictabilityResult validation in `tests/unit/test_schema.py`
- [X] T006 Implement Pydantic v2 models (no person fields) in `src/predictability/core/schema.py`
- [X] T007 [P] Write failing unit tests for working-day vs calendar-day slip, weekends, and holidays in `tests/unit/test_slip.py`
- [X] T008 Implement `CapacityCalendar` (timezone, weekend, holidays) in `src/predictability/core/calendar.py`
- [X] T009 Implement slip = completion − deadline in `src/predictability/core/slip.py` (default `working_days`; vacations MUST NOT change slip, only the capacity factor later)
- [X] T010 [P] Write failing unit tests for YAML/JSON factor and adapter config load in `tests/unit/test_config.py`
- [X] T011 Implement config loader in `src/predictability/core/config.py`
- [X] T012 [P] Write failing unit tests for SQLite create, epic upsert on `(tracker, external_id)`, children, dependencies, and artifacts in `tests/unit/test_store.py`
- [X] T013 Implement SQLAlchemy 2 SQLite store (`--db`, default `./predictability.sqlite`) in `src/predictability/store/sqlite.py`
- [X] T014 [P] Write failing unit tests for typed errors (usage, adapter, empty train, no active model) in `tests/unit/test_errors.py`
- [X] T015 Implement exception types in `src/predictability/core/errors.py`
- [X] T016 Implement entry-point registry in `src/predictability/core/registry.py`
- [X] T017 [P] Write failing contract test that PredictabilityResult and EvaluationReport schemas omit person ids/slip/ranks in `tests/contract/test_public_api_no_person_fields.py`

**Checkpoint**: Types, store, config, and errors exist; user stories can start

---

## Phase 3: User Story 1 - Predict epic deadline reliability from historical slip (Priority: P1) 🎯 MVP

**Goal**: Library `train`/`predict` on synthetic completed epics with `empirical_bayes` returns p50/p90 slip and P(on-time); late teams score worse; open epics are excluded from train.

**Independent Test**: Mock/synthetic completed epics only (no live tracker). Fit `empirical_bayes`, predict a new open epic. Inspect p50, p90, `on_time_probability`, `model_id`. No CLI required.

### Tests for User Story 1 (MANDATORY) ⚠️

> Write these tests FIRST; they MUST fail before implementation

- [X] T018 [P] [US1] Write failing unit tests for shrinkage `w = n/(n+k)`, global prior when `n < min_history`, and Gaussian/residual quantiles in `tests/unit/test_empirical_bayes.py`
- [X] T019 [P] [US1] Write failing ModelBackend contract tests (`fit`, `predict_quantiles`, `predict_on_time_proba`, `save`/`load`) in `tests/contract/test_model_protocol.py`
- [X] T020 [P] [US1] Write failing integration tests: two-team bias direction; open epics excluded from train but eligible for predict in `tests/integration/test_train_predict.py`

### Implementation for User Story 1

- [X] T021 [P] [US1] Implement synthetic completed-epic generator (two-team bias) in `src/predictability/core/synthetic.py`
- [X] T022 [P] [US1] Implement `ModelBackend` protocol and `FeatureFrame` typing in `src/predictability/models/base.py`
- [X] T023 [US1] Implement `empirical_bayes` backend in `src/predictability/models/empirical_bayes.py`
- [X] T024 [US1] Implement `PredictabilityResult` assembly (quantiles, on-time, `cold_start`, `team_history_n`, model identity; no person fields) in `src/predictability/core/score.py`
- [X] T025 [US1] Implement full-refit trainer (completed epics only) in `src/predictability/training/trainer.py`
- [X] T026 [US1] Expose library `train` and `predict` facades in `src/predictability/__init__.py`
- [X] T027 [US1] Register `empirical_bayes = "predictability.models.empirical_bayes:EmpiricalBayesBackend"` under `[project.entry-points."predictability.models"]` in `pyproject.toml`

**Checkpoint**: US1 is independently testable via library + synthetic data

---

## Phase 4: User Story 2 - Use a library and CLI without a network service (Priority: P1)

**Goal**: `ingest` / `train` / `predict` / `evaluate` work as library + CLI against SQLite. No HTTP. Structured errors. Predict from file **or** `--status open`.

**Independent Test**: `pip install` without FastAPI; mock ingest → train → predict → evaluate on synthetic epics; no listening port.

### Tests for User Story 2 (MANDATORY) ⚠️

- [X] T028 [P] [US2] Write failing CLI contract tests: subcommands, default `--db`, JSON stdout, no `serve`, exit codes 2–5, no traceback on stdout in `tests/contract/test_cli.py`
- [X] T029 [P] [US2] Write failing integration test ingest(mock) → train → predict `--file` and `--status open` → evaluate `empirical_bayes` in `tests/integration/test_cli_flow.py`
- [X] T030 [P] [US2] Write failing unit tests for mock adapter `seed` / `n_epics` / `due_changelog` in `tests/unit/test_mock_adapter.py`

### Implementation for User Story 2

- [X] T031 [P] [US2] Implement `TrackerAdapter` protocol (`fetch` → epics, children, dependencies) in `src/predictability/adapters/base.py`
- [X] T032 [US2] Implement `MockAdapter` (fixture_path + synthetic generator) in `src/predictability/adapters/mock.py`
- [X] T033 [US2] Implement library ingest (adapter → store, IngestReport) in `src/predictability/ingest.py`
- [X] T034 [US2] Implement CLI (`ingest`, `train`, `predict`, `evaluate`; union `--file` and `--status open` when both passed) in `src/predictability/cli.py`
- [X] T035 [US2] Add `src/predictability/__main__.py` (`python -m predictability`)
- [X] T036 [US2] Point `[project.scripts]` at `predictability.cli:main` and register `mock` under `predictability.adapters` in `pyproject.toml`
- [X] T037 [US2] Implement walk-forward evaluate (fit on past, score future; do **not** read/write `is_active`) in `src/predictability/evaluation/backtest.py`
- [X] T038 [US2] Implement MAE, pinball, Brier, interval coverage in `src/predictability/evaluation/metrics.py`
- [X] T039 [US2] Map errors to CLI exit codes (2 usage, 3 adapter, 4 empty train, 5 no active model); stderr diagnostics; JSON/human output per [cli.md](./contracts/cli.md) in `src/predictability/cli.py`

**Checkpoint**: US1 and US2 work independently (library score + operator CLI)

---

## Phase 5: User Story 3 - Configure and extend prediction factors (Priority: P2)

**Goal**: Enable/disable `team_bias`, `capacity_calendar`, `cross_team_deps`; custom factor plugins; expected directional effects.

**Independent Test**: Train twice on identical epics (factors off vs on); feature columns and predictions move in the specified direction. Stub plugin factor appears in the matrix.

### Tests for User Story 3 (MANDATORY) ⚠️

- [X] T040 [P] [US3] Write failing Factor protocol contract tests (`fit`/`transform`, epic-aligned rows, no leakage rule) in `tests/contract/test_factor_protocol.py`
- [X] T041 [P] [US3] Write failing integration tests: vacation overlap raises p90 slip; foreign blocker lowers on-time; disabled factors omit columns; plugin factor loads in `tests/integration/test_factors.py`
- [X] T042 [P] [US3] Write failing unit tests that `team_bias` for epic i uses only slips with `actual_completed_at` strictly before i’s deadline in `tests/unit/test_team_bias.py`
- [X] T043 [P] [US3] Write failing unit tests that vacation+weekend overlap is not double-counted in working-day mode in `tests/unit/test_capacity_calendar.py`
- [X] T044 [P] [US3] Write failing unit tests for epic∪child link rollup, `team_id` dedupe, cycle max_depth warn in `tests/unit/test_cross_team_deps.py`

### Implementation for User Story 3

- [X] T045 [P] [US3] Implement `Factor` protocol and `FactorContext` in `src/predictability/factors/base.py`
- [X] T046 [US3] Implement `team_bias` (default enabled; columns `team_n`, `team_mean_slip`, `team_std_slip`, `global_mean_slip`, `shrinkage_w`) in `src/predictability/factors/team_bias.py`
- [X] T047 [US3] Implement `capacity_calendar` (team vacations + holidays) in `src/predictability/factors/capacity_calendar.py`
- [X] T048 [US3] Implement `cross_team_deps` in `src/predictability/factors/cross_team_deps.py`
- [X] T049 [US3] Implement factor pipeline plus child-derived columns (`child_count`, `open_child_count`, …) in `src/predictability/factors/pipeline.py`
- [X] T050 [US3] Register `team_bias`, `capacity_calendar`, `cross_team_deps` under `[project.entry-points."predictability.factors"]` in `pyproject.toml`
- [X] T051 [US3] Wire factor config from `config/default.yaml` into `src/predictability/training/trainer.py` and store `factor_set_hash` on `ModelArtifact`

**Checkpoint**: US3 independently testable; GBM-ready feature matrix exists

---

## Phase 6: User Story 4 - Ingest epics from Jira, YouTrack, or a custom tracker (Priority: P2)

**Goal**: Jira and YouTrack adapters (changelog mandatory capability) plus plugin adapters; skip/flag unmapped teams and no-deadline epics; children never become predict rows.

**Independent Test**: Fixture JSON (including changelog, no live network) for mock/Jira/YouTrack share canonical fields. Stub custom adapter can ingest → train → predict.

### Tests for User Story 4 (MANDATORY) ⚠️

- [X] T052 [P] [US4] Write failing contract tests: two changelog dues → first date + `deadline_source=changelog`; no changelog → current due + `current_fallback` in `tests/contract/test_adapter_changelog.py`
- [X] T053 [P] [US4] Write failing contract tests that Jira and YouTrack fixtures emit the same canonical field set and children never appear as Epic rows in `tests/contract/test_jira_youtrack_schema.py`
- [X] T054 [P] [US4] Write failing integration test for a stub custom adapter (SC-003) in `tests/integration/test_custom_adapter.py`
- [X] T055 [P] [US4] Add changelog fixtures `tests/fixtures/jira/epic_changelog.json` and `tests/fixtures/youtrack/feature_changelog.json`

### Implementation for User Story 4

- [X] T056 [US4] Implement `JiraAdapter` (env `JIRA_TOKEN`, due changelog, `epic_done`, `team_field`) in `src/predictability/adapters/jira.py`
- [X] T057 [US4] Implement `YouTrackAdapter` (env `YOUTRACK_TOKEN`, activity/changelog) in `src/predictability/adapters/youtrack.py`
- [X] T058 [US4] Implement ingest skip counters (`skipped_no_deadline`, `skipped_unmapped_team`) and `deadline_source` in `src/predictability/ingest.py`
- [X] T059 [US4] Register `jira` and `youtrack` entry points in `pyproject.toml`
- [X] T060 [US4] Write unit tests for empty fetch, missing team map, and `test_connection` typed errors in `tests/unit/test_adapter_errors.py`

**Checkpoint**: US4 independently testable with fixtures only (no live Jira/YouTrack in default pytest)

---

## Phase 7: User Story 5 - Continue training with more history and new teams (Priority: P3)

**Goal**: Full refit from SQLite after new ingest; new artifact becomes active; unseen teams predict with `cold_start=true` until `min_history`.

**Independent Test**: Train A/B; ingest more A plus new team C; refit; C predicts with `cold_start=true`; after enough C history, `cold_start=false`.

### Tests for User Story 5 (MANDATORY) ⚠️

- [X] T061 [P] [US5] Write failing integration test cold_start then min_history flip (SC-004) in `tests/integration/test_cold_start.py`
- [X] T062 [P] [US5] Write failing integration test that a new `train` stores a new artifact and sets `is_active` (previous archived) in `tests/integration/test_refit_activate.py`
- [X] T063 [P] [US5] Write failing integration test that re-ingest of the same epics does not grow train rows by more than 1% (SC-007) in `tests/integration/test_ingest_idempotent.py`

### Implementation for User Story 5

- [X] T064 [US5] Set `cold_start` and `team_history_n` from shrinkage/`min_history` in `src/predictability/core/score.py` and `src/predictability/models/empirical_bayes.py`
- [X] T065 [US5] Enforce at most one `is_active` artifact; `train(activate=True)` default in `src/predictability/store/sqlite.py` and `src/predictability/training/trainer.py`
- [X] T066 [US5] Complete upsert-on-re-ingest and IngestReport `imported`/`updated` in `src/predictability/ingest.py` and `src/predictability/store/sqlite.py`

**Checkpoint**: Requirement 3 (continued training + cold start) is independently testable

---

## Phase 8: User Story 6 - Compare model quality and swap the learning backend (Priority: P3)

**Goal**: Walk-forward `evaluate` of `empirical_bayes` vs `quantile_catboost` and/or `quantile_lightgbm` without mutating the serving artifact; swap via `train --backend`.

**Independent Test**: Side-by-side metrics on a ≥1,000 completed-epic fixture; evaluate leaves `is_active` unchanged; subsequent `train --backend quantile_catboost` changes `predict` `backend`.

### Tests for User Story 6 (MANDATORY) ⚠️

- [X] T067 [P] [US6] Write failing contract tests: separate registry names; missing extra → clear `pip install predictability[catboost]` / `[gbm]` error in `tests/contract/test_gbm_backends.py`
- [X] T068 [P] [US6] Write failing integration test walk-forward ≥1,000 epics; report MAE/pinball/Brier/coverage; `is_active` unchanged (SC-005) in `tests/integration/test_evaluate_walkforward.py`
- [X] T069 [P] [US6] Write failing integration test evaluate-then-`train --backend B` so next predict identity is B in `tests/integration/test_backend_swap.py`
- [X] T070 [P] [US6] Write failing contract test that a stub ModelBackend plugin participates in evaluate and train in `tests/contract/test_custom_model_plugin.py`
- [X] T071 [P] [US6] Add walk-forward fixture helper (≥1,000 completed epics) in `tests/fixtures/walkforward.py`

### Implementation for User Story 6

- [X] T072 [P] [US6] Implement `quantile_catboost` in `src/predictability/models/quantile_catboost.py` (do **not** share a wrapper class with LightGBM)
- [X] T073 [P] [US6] Implement `quantile_lightgbm` in `src/predictability/models/quantile_lightgbm.py`
- [X] T074 [US6] Register both GBM names under `[project.entry-points."predictability.models"]` in `pyproject.toml`
- [X] T075 [US6] Persist `EvaluationReport` / `EvaluationRow` (`artifact_id` null); missing GBM extra → error row, other backends still complete in `src/predictability/evaluation/backtest.py`
- [X] T076 [US6] Print JSON EvaluationReport on stdout and TTY table on stderr from `evaluate` in `src/predictability/cli.py`

**Checkpoint**: Requirement 4 (compare + swap libraries) is independently testable; bias baseline remains in evaluate

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Quickstart, coverage, public-API invariants, quality gates

- [X] T077 [P] Add `tests/fixtures/sample_open_epics.json` for [quickstart.md](./quickstart.md) Scenario B
- [X] T078 [P] Update `README.md` install/CLI examples to match quickstart Scenarios A, B, D–H (skip C / `serve`)
- [X] T079 Extend `tests/contract/test_cli.py` to assert `serve` is not a subcommand
- [X] T080 [P] Add unit tests for any remaining untested public functions under `tests/unit/` until `src/predictability` coverage ≥ 90%
- [X] T081 Run [quickstart.md](./quickstart.md) Scenarios A, B, D, E, F, G, H against a local SQLite file
- [X] T082 Run `pre-commit run --all-files` (ruff, mypy, pytest `--cov-fail-under=90`) per `.pre-commit-config.yaml` and `.github/workflows/ci.yml`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately
- **Foundational (Phase 2)**: Depends on Setup — **blocks all user stories**
- **US1 (Phase 3)**: Depends on Foundational only — MVP
- **US2 (Phase 4)**: Depends on Foundational; uses US1 `train`/`predict` internally but is tested via CLI + mock ingest
- **US3 (Phase 5)**: Depends on Foundational + US1 trainer hook; independently testable with synthetic epics
- **US4 (Phase 6)**: Depends on Foundational + US2 ingest; independently testable with fixtures
- **US5 (Phase 7)**: Depends on US1 predict + US2 ingest/train
- **US6 (Phase 8)**: Depends on US2 evaluate skeleton + US1 registry; GBM extras optional at runtime
- **Polish (Phase 9)**: After stories intended for the release

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — no other stories
- **US2 (P1)**: After Phase 2 — needs US1 library train/predict for a meaningful CLI; mock adapter is US2-owned
- **US3 (P2)**: After Phase 2 — trainer must accept a factor pipeline (US1 can train with empty/identity features until T051)
- **US4 (P2)**: After US2 ingest surface
- **US5 (P3)**: After US1 + US2
- **US6 (P3)**: After US2 evaluate command exists

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models/protocols before backends
- Trainer before CLI
- Story complete before moving to next priority unless staffed in parallel on different files

### Parallel Opportunities

- Phase 1: T002, T003, T004 after T001
- Phase 2: T005/T007/T010/T012/T014/T017 in parallel; T008 before T009
- US1 tests T018–T020 in parallel; T021–T022 in parallel after tests
- US3 tests T040–T044 in parallel; T046–T048 after T045
- US4 tests T052–T055 in parallel; T056 and T057 in parallel
- US6 T072 and T073 in parallel (separate files, separate extras)

---

## Parallel Example: User Story 1

```bash
# Tests together:
Task: "Write failing unit tests in tests/unit/test_empirical_bayes.py"
Task: "Write failing ModelBackend contract tests in tests/contract/test_model_protocol.py"
Task: "Write failing integration tests in tests/integration/test_train_predict.py"

# Then implementations that do not share files:
Task: "Synthetic generator in src/predictability/core/synthetic.py"
Task: "ModelBackend protocol in src/predictability/models/base.py"
```

---

## Parallel Example: User Story 6

```bash
Task: "quantile_catboost in src/predictability/models/quantile_catboost.py"
Task: "quantile_lightgbm in src/predictability/models/quantile_lightgbm.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup
2. Phase 2 Foundational
3. Phase 3 US1 (`empirical_bayes` library train/predict)
4. **STOP and VALIDATE** using spec Independent Test for US1 (synthetic two-team bias)
5. Demo without CLI or HTTP

### Incremental Delivery

1. Setup + Foundational
2. US1 → library MVP
3. US2 → CLI + SQLite + mock ingest (P1 operator path)
4. US3 → factors
5. US4 → Jira/YouTrack fixtures
6. US5 → refit + cold start
7. US6 → GBM compare + swap
8. Polish / quickstart A–H (not C)

### Parallel Team Strategy

1. Shared: Phase 1–2
2. After foundation:
   - A: US1 then US5
   - B: US2 then US4
   - C: US3 then US6 (needs trainer + evaluate hooks)

---

## Notes

- [P] = different files, no unfinished deps
- Do not add `src/predictability/api/`, FastAPI, Docker, or `serve`
- Do not collapse CatBoost and LightGBM into one registry name
- Default pytest: fixtures only — no live Jira/YouTrack
- Commit after each task or logical group
- Verify tests fail before implementing
