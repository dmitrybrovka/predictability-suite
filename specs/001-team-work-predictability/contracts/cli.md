# CLI and library contract (v1)

**Feature**: `001-team-work-predictability`  
v1 public surface. HTTP is [openapi.yaml](./openapi.yaml) (**v2 / not implemented in this feature**).

## Library

Package `predictability` MUST expose (names may be thin facades):

- ingest adapter → SQLite
- `train(backend, db, activate=True)`
- `predict(db | epics, model_id=None)`  # None → active artifact
- `evaluate(db, backends, …)` → `EvaluationReport` (walk-forward)

## CLI

```text
predictability ingest  --adapter <name> [--query JSON] [--db PATH]
predictability train   --backend <name> [--db PATH] [--activate/--no-activate]
predictability predict [--file PATH] [--status open] [--db PATH] [--model-id ID]
predictability evaluate --backends empirical_bayes,quantile_catboost[,quantile_lightgbm] [--db PATH]
```

Default `--db`: `./predictability.sqlite`.

There is **no** `serve` command in v1.

### ingest

Writes epics, children, dependencies. Prints [IngestReport](../data-model.md#ingestreport) as JSON (and a one-line human summary on stderr).

### train

Full refit from completed epics in the store. Default `--activate`. Exit non-zero if backend extra missing.

### predict

Exactly one of: `--file` (canonical epic list JSON/YAML) or store filter `--status open` (may combine: file rows union store, or require one — implementer picks **union if both passed**, document it). Uses **active** artifact unless `--model-id`.

Stdout: JSON list of [PredictabilityResult](../data-model.md#predictabilityresult).

### evaluate

Walk-forward comparison. **Must not** read/write `is_active`. Stdout: JSON [EvaluationReport](../data-model.md#evaluationreport) plus a TTY table on stderr.

If a listed GBM extra is missing: that row is an error object; other backends still complete (including `empirical_bayes`).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | success |
| 2 | usage / config |
| 3 | adapter / tracker |
| 4 | empty/insufficient train set |
| 5 | no active model (predict) |
