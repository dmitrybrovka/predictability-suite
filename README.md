# Predictability Suite

Python library and CLI that estimates **team work predictability** from
epic-level deadline slip (first changelog due date vs actual completion).

v1 is a local library + CLI over SQLite. HTTP service is v2.

Spec: [`specs/001-team-work-predictability/spec.md`](specs/001-team-work-predictability/spec.md).
Constitution: [`.specify/memory/constitution.md`](.specify/memory/constitution.md).

## Requirements

- Python 3.11+ (3.12 recommended)

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

Optional extras for model backends: `pip install -e ".[dev,catboost,gbm]"`.

## Quality gates

These run on every `git commit` via pre-commit, and on every push and pull
request via GitHub Actions. Run them yourself with:

```bash
ruff check src tests
ruff format src tests
python -m mypy
python -m pytest
pre-commit run --all-files
```

| Gate | Tool | Config |
|------|------|--------|
| Lint | Ruff | `pyproject.toml` `[tool.ruff]` |
| Format | Ruff | `ruff format` |
| Types | mypy (strict) | `[tool.mypy]` |
| Tests | pytest | `[tool.pytest.ini_options]` |
| Coverage | pytest-cov, ≥ 90% | pre-commit and CI |

Plain `python -m pytest` does not enforce coverage, so a single-file run during
red-green-refactor is not blocked by total coverage. The 90% threshold is
applied by the pre-commit hook and CI:

```bash
python -m pytest --cov=predictability --cov-report=term-missing --cov-fail-under=90
```

Local mypy/pytest hooks run through `scripts/venv-python`, which uses `.venv`
(or an active `VIRTUAL_ENV`) and fails loudly rather than falling back to a
system interpreter.

Whitespace hooks skip `.specify/` and `.cursor/skills/`: those are vendored
spec-kit assets tracked by hash in `.specify/integrations/*.manifest.json`.

Do not add a second Python linter or formatter. Tests are required for all
production code (constitution III). Default pytest MUST NOT call live trackers.

## Layout

```text
src/predictability/     # library
tests/unit/
tests/contract/
tests/integration/
.pre-commit-config.yaml
pyproject.toml
```

## License

MIT
