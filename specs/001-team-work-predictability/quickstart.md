# Quickstart: validate Team Work Predictability (post-implement)

**Feature**: `001-team-work-predictability`  
**Purpose**: Runnable checks that v1 works end-to-end. Not an implementation guide.

Public surface: [contracts/cli.md](./contracts/cli.md). HTTP/[openapi.yaml](./contracts/openapi.yaml) is **v2 — skip**.

## Prerequisites

- Python 3.11+ (3.12 recommended)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[catboost]"
# optional: pip install -e ".[catboost,gbm]" to compare LightGBM too
```

No outbound network for the scenarios below (mock adapter).

## Scenario A — Library: bias baseline on synthetic epics

1. Mock completed **epics** for two teams with different slip bias ([Epic](./data-model.md#epic)).
2. Fit default factors + `empirical_bayes`.
3. Predict a new **open epic** per team with the same deadline.

**Expect**: `PredictabilityResult` with p50/p90, `on_time_probability`, `model_id`. Late team has lower on-time probability. `cold_start` false when `n ≥ min_history`. No person fields.

## Scenario B — CLI: ingest → train → predict → evaluate

```bash
predictability ingest --adapter mock --query '{"seed": 42, "n_teams": 3, "n_epics": 1200}'
predictability train --backend empirical_bayes
predictability predict --file sample_open_epics.json
predictability predict --status open
predictability evaluate --backends empirical_bayes,quantile_catboost
```

**Expect**:

- Ingest `imported >= 1000` epics; re-ingest does not grow train rows > 1% (SC-007).
- Both predict paths return results; `backend` is `empirical_bayes` after that train.
- Evaluate prints two rows (MAE, pinball@p90, Brier). **Active artifact unchanged** (still the train from step 2). Evaluate is not a predict of that artifact.
- If CatBoost extra missing: that evaluate row errors; `empirical_bayes` still reported.

## Scenario C — HTTP *(v2 — do not run in v1)*

`predictability serve` MUST NOT exist in v1. Skip SC-006.

## Scenario D — Factors (team vacation + deps)

Same epic history:

1. Team vacation overlapping the committed window vs none → p90 slip **up**.
2. Foreign-team blocker on epic or child vs none → on-time probability **down**.

`team_bias` columns present when the factor is enabled (FR-019).

## Scenario E — Custom adapter

Stub adapter per [adapter-protocol.md](./contracts/adapter-protocol.md) including a two-entry due changelog → first date wins. ingest → train → predict without editing `core/` or `models/` (SC-003).

## Scenario F — Cold start

Train on A/B. Predict unseen team C. **Expect** success, `cold_start=true`. After ≥ `min_history` C epics and refit, `cold_start=false`.

## Scenario G — Swap library

`evaluate` then `train --backend quantile_catboost`. **Expect** subsequent `predict` `backend=quantile_catboost`. Evaluate alone must not have switched it.

## Scenario H — Changelog fallback

Fixture epic with no changelog, current due present. **Expect** ingest `deadline_source=current_fallback`, item still trainable.

## Out of scope for this file

Live Jira/YouTrack, Docker, SSO, v2 HTTP.
