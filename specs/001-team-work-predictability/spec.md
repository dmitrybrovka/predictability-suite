# Feature Specification: Team Work Predictability Suite

**Feature Branch**: `001-team-work-predictability`

**Created**: 2026-08-24

**Status**: Clarified (grill-me 2026-08-24)

**Input**: User description: "Нужно сделать opensource пакет с предиктивной моделью оценки Team Work Predictability на основе расхождения дедлайна установленного командой и фактической даты выполнения. Требования: (1) конфигурировать модель факторами — индивидуальные особенности команды, взаимосвязи между командами, график отпусков и т.п.; (2) адаптеры для Task Tracker API — Jira, YouTrack и др.; (3) дообучение модели на новых исторических данных и новых командах; (4) сравнение качества моделей и замена библиотеки; (5) простой API и сервис, легко разворачиваемый во внутреннем контуре."

## Clarifications *(grill-me)*

- Prediction grain is **epic/feature**, not tracker issue and not person.
- Atomic outputs: slip quantiles (p50, p90) + P(on-time). Team/sprint figures are aggregations.
- **v1** = Python library + CLI. **Requirement 5 (HTTP service) is v2.**
- Public API MUST NOT expose person-level slip or ranking. Vacations are **team** capacity.
- Team-committed deadline = **first due date in changelog**, else current due with `deadline_source` flag.
- Epic completion rule is adapter config `epic_done: own | children | own_then_children` (default `own_then_children`).
- Child issues are **factors only**, never prediction objects.
- `evaluate` is **walk-forward backtest** (re-fit on past, score future). It does **not** call the serving artifact. `predict` calls the serving artifact.
- Model registry v1: `empirical_bayes` (bias baseline, always first-class), `quantile_catboost`, `quantile_lightgbm`.
- Last successful `train` (activate-by-default) is what `predict` uses.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Predict epic deadline reliability from historical slip (Priority: P1)

A delivery analyst provides completed **epics/features** that have a team-committed deadline and an actual completion date. The system estimates slip (deadline vs actual), a distribution of likely completion, and the probability that an **open** epic will finish by its committed date. Team-level figures are aggregations of epic predictions, not a separate model.

**Why this priority**: This is the product's core value. Without a usable predictability signal from deadline slip, adapters and factors have nothing to serve.

**Independent Test**: Using only a mock/synthetic completed-epic dataset (no live tracker), train `empirical_bayes` and predict for a new open epic. Success is inspectable p50/p90 slip plus on-time probability.

**Acceptance Scenarios**:

1. **Given** a history of completed epics with committed deadline and actual completion, **When** a user trains the default backend and predicts for a new epic with a committed deadline, **Then** the system returns slip quantiles (at least p50 and p90) and an on-time probability.
2. **Given** two teams with different historical bias (one systematically late, one on time), **When** the same epic attributes are predicted for each team, **Then** the late team's on-time probability is lower and its expected slip is larger.
3. **Given** epics missing actual completion (still open), **When** training runs, **Then** those epics are excluded from the supervised target and do not crash training; they remain eligible for `predict`.

---

### User Story 2 - Use a library and CLI without a network service (Priority: P1)

A platform engineer installs the package inside the company network (no mandatory cloud). They run ingest, train, predict, and evaluate through a Python library API and a CLI. No HTTP server is required in v1.

**Why this priority**: Library-first is the v1 adoption path. Requirement 5 (intranet HTTP) is explicitly deferred to v2.

**Independent Test**: Install from a local wheel **without** FastAPI extras, point CLI at a SQLite file, run ingest (mock) → train → predict → evaluate on synthetic epics.

**Acceptance Scenarios**:

1. **Given** a machine with no internet after package install and no `[api]` extra, **When** the operator runs CLI train/predict against default SQLite, **Then** the flow succeeds without outbound SaaS or a listening HTTP port.
2. **Given** a trained artifact, **When** the operator runs `predict` from a canonical JSON file **or** from open epics in the store, **Then** each result includes team_id, slip quantiles, on-time probability, and model identity (backend + artifact id).
3. **Given** invalid payloads (missing deadline, unknown backend name), **When** CLI/library is invoked, **Then** the process exits with a structured error (non-zero CLI status) without leaking a traceback to stdout.

---

### User Story 3 - Configure and extend prediction factors (Priority: P2)

A delivery analyst enables, disables, and parameterizes factors: team-specific estimation **bias**/variance, cross-team dependency load (epic links **and** rolled-up child links, deduped by `team_id`), and team vacation capacity. A developer can add a new factor without changing the training loop.

**Why this priority**: Requirement 1 is the main customization surface after the core score exists.

**Independent Test**: Train twice on identical epics, once with vacations/dependencies disabled and once enabled; assert feature columns and predictions change in the expected direction. Register a stub custom factor and see it in the feature matrix.

**Acceptance Scenarios**:

1. **Given** a YAML/JSON factor config listing `team_bias`, `capacity_calendar`, and `cross_team_deps`, **When** training runs, **Then** the feature matrix contains columns from each enabled factor and omits disabled ones.
2. **Given** an epic whose committed window overlaps a **team** vacation interval, **When** `capacity_calendar` is enabled, **Then** predicted slip increases relative to the same epic with no vacation overlap.
3. **Given** an epic (or its children) blocked by unfinished work from another team, **When** `cross_team_deps` is enabled, **Then** predicted on-time probability is lower than for an otherwise identical unblocked epic.
4. **Given** a third-party factor registered via the package plugin entry point, **When** it is named in config, **Then** training loads it without modifying core source.

---

### User Story 4 - Ingest epics from Jira, YouTrack, or a custom tracker (Priority: P2)

An integrator maps a task tracker into a canonical **epic** schema (plus child issues for features). Built-in adapters cover Jira and YouTrack and **must** read due-date changelog. A company with a different tracker writes an adapter that implements the same contract.

**Why this priority**: Requirement 2 is how historical slip data arrives.

**Independent Test**: Mock adapter plus fixture-based Jira/YouTrack adapters (synthetic JSON including changelog; no live network in CI) emit the same canonical epic fields. A stub custom adapter can train.

**Acceptance Scenarios**:

1. **Given** Jira-like epic JSON plus changelog of due dates and child issues, **When** the Jira adapter normalizes it, **Then** the epic has `external_id`, `team_id`, `committed_deadline` from **first changelog due date** (else current due + `deadline_source=current_fallback`), `actual_completed_at` per `epic_done` rule, and child/dependency records for factors.
2. **Given** YouTrack-like feature JSON with equivalent history, **When** the YouTrack adapter normalizes it, **Then** the canonical schema matches the Jira adapter's output shape (including changelog-derived deadline).
3. **Given** a custom adapter implementing the tracker protocol, **When** it is registered and selected in config, **Then** ingest → store → train → predict works with no core code changes.
4. **Given** an epic that cannot map `team_id` or has no deadline even as current due, **When** ingest runs, **Then** it is skipped or flagged, counted in the ingest report, and does not enter the training set.

---

### User Story 5 - Continue training with more history and new teams (Priority: P3)

An operator appends newly completed epics and onboards a team that was not in the original training set. The trainer **refits from the full SQLite history**. New teams with little history receive a global prior until enough local data exists.

**Why this priority**: Requirement 3 is how the product stays current.

**Independent Test**: Train on teams A and B; ingest more A epics plus a new team C with few epics; refit; A predictions may shift, C predictions succeed with `cold_start=true`.

**Acceptance Scenarios**:

1. **Given** a stored history and a trained artifact, **When** a new completed-epic batch is ingested and `train` runs, **Then** a new model version is stored and becomes the active artifact for `predict` (activate-by-default).
2. **Given** a brand-new `team_id` with fewer than the configured minimum completed epics, **When** a prediction is requested, **Then** the system uses a global prior, returns `cold_start=true`, and does not fail.
3. **Given** the new team later exceeds the minimum history threshold, **When** the model is refit, **Then** subsequent predictions rely primarily on that team's own slip history.

---

### User Story 6 - Compare model quality and swap the learning backend (Priority: P3)

A data scientist runs **walk-forward `evaluate`** on the same time-ordered epic history for `empirical_bayes` vs `quantile_catboost` and/or `quantile_lightgbm`, reads comparable metrics, then `train --backend <winner>` so the next `predict` uses that library. `evaluate` does not score or replace the current serving artifact.

**Why this priority**: Requirement 4. Bias baseline must remain first-class so GBM libraries can be beaten on small data.

**Independent Test**: Walk-forward on a synthetic process with known team bias. Side-by-side table includes the Bayes baseline and at least one GBM. Switching happens via a subsequent `train`, not via evaluate.

**Acceptance Scenarios**:

1. **Given** registered backends including `empirical_bayes` and at least one of `quantile_catboost` / `quantile_lightgbm`, **When** `evaluate` runs, **Then** the report includes MAE of expected slip, pinball loss for advertised quantiles, on-time Brier (or log-loss), and interval coverage, **and** evaluate does not change `is_active` on stored artifacts.
2. **Given** an evaluation report where backend B beats backend A on p90 pinball, **When** the operator runs `train --backend B`, **Then** subsequent `predict` results show B's model identity.
3. **Given** a user-supplied backend that implements the model protocol, **When** it is registered, **Then** it participates in `evaluate` and can be selected for `train`.

---

### Edge Cases

- Epic has a committed deadline but no completion: excluded from training; eligible for prediction (from file or store).
- Actual completion before committed deadline (negative slip): valid.
- Changelog unavailable: use current due date and set `deadline_source=current_fallback`; do not fail the whole ingest.
- `epic_done=own` but epic has no resolution: skip from train unless fallback mode includes children.
- Circular or missing dependency links: factor degrades (zero extra risk, warning).
- Team vacation overlapping weekends/holidays: capacity factor must not double-count non-working days when slip unit is working days.
- Duplicate `(tracker, external_id)` on re-ingest: upsert.
- Extremely small dataset: `empirical_bayes` still trains; GBM extras may warn or refuse with a clear error.
- Tracker rate limits / auth failure: ingest aborts with a typed error; partial pages are not “full history” unless `allow_partial`.
- Child issues MUST NOT appear as `predict` rows.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST compute slip on each **completed epic** as signed (actual completion − team-committed deadline) in a configured unit (default working days; calendar days optional).
- **FR-002**: System MUST output expected slip, quantiles p50 and p90 (config may add more), and P(actual completion on or before committed deadline).
- **FR-003**: System MUST persist canonical epics, child records used as factors, factor config, model artifacts, and evaluation reports in a local **SQLite** file (CLI `--db`, default `./predictability.sqlite`).
- **FR-004**: System MUST expose a factor pipeline configured independently of the learning backend (enable/disable, parameters, custom plugins).
- **FR-005**: System MUST ship built-in factors `team_bias`, `capacity_calendar` (team vacation YAML + optional org holidays), and `cross_team_deps` (epic links ∪ child-link rollup, dedupe by `team_id`).
- **FR-006**: System MUST define a tracker-agnostic canonical **epic** schema plus child-issue records for features; adapters map third-party payloads into that schema.
- **FR-007**: System MUST provide Jira and YouTrack adapters that read **due-date changelog**, plus a mock adapter. Default CI MUST use fixtures, not live APIs.
- **FR-008**: System MUST allow third-party adapters via plugin entry points.
- **FR-009**: System MUST update models by **full refit** from stored completed epics after new ingest (optional `partial_fit` only if a backend implements it).
- **FR-010**: System MUST predict for a previously unseen team via shrinkage / global prior and `cold_start` until `min_history` is met.
- **FR-011**: System MUST provide a model protocol and registry. v1 names: `empirical_bayes`, `quantile_catboost`, `quantile_lightgbm`.
- **FR-012**: `evaluate` MUST be walk-forward (fit on past, score future) and MUST NOT use or mutate the serving artifact. Primary ranking metric: p90 pinball; tie-break Brier on-time.
- **FR-013**: System MUST expose ingest, train, predict, and evaluate via Python library and CLI. HTTP/OpenAPI is **out of scope for v1** (v2 / requirement 5).
- **FR-014**: `predict` MUST use the last successful `train` artifact (activate-by-default) and MUST accept canonical epic JSON/YAML **or** open epics from the store.
- **FR-015**: System MUST record model identity (name, version, factor-set hash, training data cutoff) on every prediction and evaluation report.
- **FR-016**: Ingest MUST report imported/updated/skipped/invalid counts, upsert on `(tracker, external_id)`, and record `deadline_source` (`changelog` | `current_fallback`).
- **FR-017**: Adapter config MUST include explicit `team_id` mapping, epic type/field list, and `epic_done` (default `own_then_children`).
- **FR-018**: Public outputs MUST NOT include per-person slip, ranking, or performance scores.
- **FR-019**: `team_bias` MUST remain a default-on factor for GBM backends; `empirical_bayes` MUST remain a comparable backend in `evaluate` (bias is not only a GBM feature).

### Key Entities

- **Epic**: Canonical prediction unit. Tracker, external id, team id, committed deadline, deadline_source, actual completion, status, children ids, epic-level links.
- **ChildIssue**: Non-predicted record under an epic; used for completion fallback, size/remaining features, and dependency rollup.
- **Team**: Deadline-setting group; `team_id` from adapter mapping only (no inferred org chart).
- **Slip**: Signed lateness of a completed Epic.
- **Factor**: Named transform from epics + context into features.
- **CapacityCalendar**: Timezone, weekend, optional holidays; **team** vacation intervals (not person-level in v1).
- **Dependency**: Directed link on epic or child; factor aggregates foreign `team_id`.
- **ModelBackend**: `empirical_bayes` | `quantile_catboost` | `quantile_lightgbm` | plugin.
- **ModelArtifact**: Serialized backend + factor state + metadata; at most one `is_active`.
- **EvaluationReport**: Walk-forward comparison; independent of the active artifact.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Install to first prediction on synthetic epics (library or CLI) in under 15 minutes, without starting an HTTP server.
- **SC-002**: On a synthetic set with known team bias, team-vacation shocks, and cross-team blocking, enabling the matching factors improves p90 pinball vs a no-factor run by a documented margin in the evaluation fixture.
- **SC-003**: A custom adapter that only implements the documented protocol can complete ingest → train → predict without changing core packages.
- **SC-004**: Predicting for a new team with fewer than `min_history` epics succeeds with `cold_start=true` in 100% of fixtures.
- **SC-005**: Walk-forward `evaluate` of `empirical_bayes` and at least one GBM completes on a fixture of ≥ 1,000 **completed epics** and emits a side-by-side table; the active serving artifact is unchanged.
- **SC-006**: *(v2)* HTTP service start + OpenAPI — **not a v1 success criterion**.
- **SC-007**: Idempotent re-ingest of the same epics does not grow training row count by more than 1%.

## Assumptions

- Target users run Python 3.11+ on Linux/macOS inside a private network.
- v1 trains on **completed epics only**; survival/censoring is out of v1.
- Epic identity is configured (`issue_types` / YouTrack type or tag), not inferred as “anything with children”.
- Team identity is only an adapter field map.
- Default slip unit is working days (Sat/Sun + optional holiday file + timezone).
- Full refit is enough at intended scale (thousands of epics plus children).
- Jira/YouTrack live calls are optional integration tests; CI is fixtures including changelog samples.
- One SQLite file serves one organization; no multi-tenant SaaS.
- No UI. MIT license.
- HTTP/Docker/OpenAPI belong to v2 (requirement 5).

## Scope Boundaries

- **In scope (v1)**: Canonical epic + children, factor pipeline (including team bias), model registry (Bayes + CatBoost + LightGBM), Jira/YouTrack/mock adapters with changelog, SQLite store, CLI + library, walk-forward evaluate.
- **Out of scope (v1)**: HTTP service, OpenAPI server, `serve` command, Docker-as-product, web UI, person scoring, SSO, streaming ingest, org-chart inference, survival models.
- **v2**: Requirement 5 — simple HTTP API for internal contour.
