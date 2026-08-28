# API inventory

This file is the mkdocstrings **source list**, not the generated HTML.
Private names (`_…`) are filtered out. ORM table classes are omitted on
purpose; use [`Store`][predictability.store.sqlite.Store].

Build the site after `pip install -e ".[docs]"`:

```bash
mkdocs serve
```

## Library

::: predictability

::: predictability.cli

::: predictability.ingest

::: predictability.training.trainer
    options:
      members:
        - train
        - predict
        - completed_for_train

::: predictability.evaluation.backtest
    options:
      members:
        - evaluate

::: predictability.evaluation.metrics

::: predictability.store.sqlite.Store

::: predictability.store.sqlite.DEFAULT_DB

## Schemas and config

::: predictability.core.schema

::: predictability.core.config

::: predictability.core.calendar

::: predictability.core.slip

::: predictability.core.errors

## Adapters

::: predictability.adapters.base

::: predictability.adapters.mock

::: predictability.adapters.jira

::: predictability.adapters.youtrack

## Factors

::: predictability.factors.base

::: predictability.factors.pipeline
    options:
      members:
        - factor_set_hash
        - effective_factor_specs
        - instantiate
        - build_matrix

::: predictability.factors.team_bias

::: predictability.factors.capacity_calendar
    options:
      members:
        - CapacityCalendarFactor
        - calendar_from_config
        - load_vacations
        - load_holidays

::: predictability.factors.cross_team_deps

## Models

::: predictability.models.base

::: predictability.models.empirical_bayes
    options:
      members:
        - EmpiricalBayesBackend
        - identity_frame

::: predictability.models.quantile_catboost
    options:
      members:
        - QuantileCatBoostBackend

::: predictability.models.quantile_lightgbm
    options:
      members:
        - QuantileLightGBMBackend
