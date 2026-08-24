<!--
Sync Impact Report
- Version change: (unratified template) → 1.0.0 (MAJOR: first ratification)
- Modified principles: placeholders → I. Library-First; II. CLI Interface;
  III. Test-First; IV. Contract and Integration Testing; V. Quality Gates;
  VI. Simplicity
- Added sections: Engineering Standards; Development Workflow; Governance (filled)
- Removed sections: none (template slots replaced)
- Templates requiring updates:
  - .specify/templates/plan-template.md ✅
  - .specify/templates/spec-template.md ✅
  - .specify/templates/tasks-template.md ✅
  - .specify/templates/checklist-template.md ✅
  - .specify/templates/commands/*.md ⚠ none present (Cursor skills used instead)
  - README.md ✅
  - specs/001-team-work-predictability/plan.md ✅
  - specs/001-team-work-predictability/research.md ✅
  - .cursor/skills/speckit-tasks/SKILL.md ✅ (tests made mandatory)
- Follow-up TODOs: none
-->

# Predictability Suite Constitution

## Core Principles

### I. Library-First

Every v1 feature MUST ship as an importable library under `src/predictability/`.
A feature is not done if it exists only as a script, notebook, or HTTP handler.
The library MUST be independently testable without a running server, cloud
account, or live task tracker. HTTP (`serve`, FastAPI, OpenAPI runtime) is v2
and MUST NOT be introduced as a v1 dependency.

**Rationale**: Intranet service deploy is deferred; the adoption path is
`pip install` plus a CLI on an air-gapped laptop.

### II. CLI Interface

Every library capability that operators use MUST be reachable from the CLI
(`ingest`, `train`, `predict`, `evaluate` in v1). Text protocol: arguments and
optional stdin in; structured results on stdout; diagnostics and errors on
stderr. The CLI MUST support JSON output for machines and a human-readable
default. Non-zero exit status on failure. No traceback on stdout.

**Rationale**: CLI is the v1 operator surface and the integration-test harness.

### III. Test-First (NON-NEGOTIABLE)

Production code MUST NOT land without automated tests. For each user story,
contract/unit/integration tests MUST be written first, MUST fail against the
unbuilt behavior, then MUST pass after implementation (red-green-refactor).
Every new module, public function, protocol implementation, CLI command, and
bugfix MUST add or extend tests. Default CI and pre-commit MUST run the suite.
Coverage of `src/predictability` MUST stay at or above 90% (`--cov-fail-under=90`).
Live network calls to Jira/YouTrack MUST NOT run in the default test suite;
use fixtures (including changelog).

**Rationale**: Predictability scores are trusted numbers. Untested slip, factor,
or adapter code is a product defect.

### IV. Contract and Integration Testing

Changes to adapter, factor, model, or CLI protocols MUST include contract tests
against the files in `specs/*/contracts/`. Integration tests MUST cover
ingest → train → predict → evaluate on the mock adapter and walk-forward
evaluation. Custom plugin entry points (factors, adapters, models) MUST have a
registration contract test. OpenAPI is a v2 contract; do not implement it in v1,
but do not silently delete the filed spec.

**Rationale**: The extension surface is the product. Protocol drift without
tests breaks third-party adapters.

### V. Quality Gates (NON-NEGOTIABLE)

Every commit MUST pass the configured quality gates:

1. **Lint**: Ruff (`ruff check`)
2. **Format**: Ruff formatter (`ruff format`); Ruff is the only formatter
3. **Types**: mypy in strict mode on `src/` and `tests/`
4. **Tests**: pytest, with coverage fail-under 90% enforced by pre-commit and CI

These MUST run via pre-commit on `git commit` and in CI on every push and pull
request, and MUST be runnable locally as the same commands. Do not add a second
linter or formatter (no Black, isort, flake8, or prettier-for-python). Do not
use `--no-verify` to skip hooks except for an explicitly documented emergency,
which MUST be followed by a fix commit.

**Rationale**: One toolchain, one local gate, no style bikeshedding.

### VI. Simplicity

Prefer the simplest design that meets the spec. v1 MUST use SQLite, full refit,
epic-level prediction, and team (not person) signals. Do not add Redis, Kafka,
SSO, containers-as-product, person-level scores, or a second prediction grain.
New libraries and extra moving parts MUST be justified in the plan Complexity
Tracking table. YAGNI: do not build v2 HTTP in v1.

**Rationale**: Complexity that is not required by a ratified requirement is
rejected.

## Engineering Standards

- **Language**: Python 3.11+ (develop and CI on 3.12).
- **Layout**: `src/predictability/` library; `tests/{unit,contract,integration}/`.
- **Config**: `pyproject.toml` is the single tool config (pytest, ruff, mypy,
  coverage). `.pre-commit-config.yaml` pins hook versions. Vendored spec-kit
  assets under `.specify/` and `.cursor/skills/` MUST NOT be reformatted by
  hooks; they are hash-tracked in `.specify/integrations/*.manifest.json`.
- **Dependencies**: Core extras-free except the HTTP client used by adapters.
  Optional extras: `[catboost]`, `[gbm]`. Dev extra: `[dev]` (pytest, ruff,
  mypy, pre-commit).
- **Public API**: MUST NOT expose person-level slip, ranking, or identity.
- **License**: MIT.

## Development Workflow

1. Install: `pip install -e ".[dev]"` then `pre-commit install`.
2. Specify → plan → tasks before large implementation (spec-kit).
3. Write failing tests → implement → refactor.
4. `pre-commit run --all-files` (or a normal `git commit`) MUST pass before
   a change is considered complete.
5. Pull requests MUST show the same gates green. Reviewers MUST reject
   untested production code and unexplained complexity.

## Governance

This constitution supersedes informal practice, README shortcuts, and
tool defaults when they conflict. Amendments require: (1) an explicit
edit to this file, (2) a semantic version bump, (3) propagation to
dependent templates and Cursor rules, (4) a note in the Sync Impact
Report. MAJOR: remove or redefine a principle. MINOR: add a principle
or materially expand a gate. PATCH: wording and non-semantic fixes.

Compliance review: every plan's Constitution Check, every `/speckit-analyze`
run, and every PR review MUST verify these principles. Runtime guidance
for agents lives in `.cursor/rules/` and MUST stay consistent with this
file. If they drift, this file wins.

**Version**: 1.0.0 | **Ratified**: 2026-08-24 | **Last Amended**: 2026-08-24
