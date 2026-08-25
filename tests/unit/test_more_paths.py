from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from predictability.adapters.base import AdapterResult, first_changelog_due
from predictability.adapters.jira import JiraAdapter
from predictability.adapters.mock import MockAdapter
from predictability.adapters.youtrack import YouTrackAdapter
from predictability.cli import main
from predictability.core.config import AppConfig
from predictability.core.errors import (
    AdapterAuthError,
    EmptyTrainSetError,
    NoActiveModelError,
    UsageError,
)
from predictability.core.schema import ChildIssue, Dependency, Epic, FactorSpec
from predictability.core.score import build_results
from predictability.core.slip import compute_slip
from predictability.core.synthetic import make_epic, two_team_history
from predictability.evaluation.metrics import brier, interval_coverage, mae, pinball
from predictability.factors.base import FactorContext
from predictability.factors.capacity_calendar import load_holidays, load_vacations
from predictability.factors.cross_team_deps import CrossTeamDepsFactor
from predictability.factors.pipeline import instantiate
from predictability.ingest import ingest, register_adapter
from predictability.models.empirical_bayes import EmpiricalBayesBackend
from predictability.store.sqlite import Store
from predictability.training.trainer import _backend_cls, predict, train


def test_metrics_empty() -> None:
    empty = np.array([], dtype=float)
    assert np.isnan(mae(empty, empty))
    assert np.isnan(pinball(empty, empty, 0.9))
    assert np.isnan(brier(empty, empty))
    assert np.isnan(interval_coverage(empty, empty, empty))


def test_slip_requires_dates() -> None:
    epic = make_epic(external_id="E", team_id="t", slip_days=1, open_item=True)
    with pytest.raises(UsageError):
        compute_slip(epic)


def test_changelog_skips_empty_due() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    due, source = first_changelog_due([(ts, None), (ts, "2026-02-01T00:00:00+00:00")])
    assert source == "changelog"
    assert due is not None
    assert due.month == 2


def test_config_invalid_root(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(UsageError):
        AppConfig.load(path)


def test_config_unreadable_or_malformed(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="cannot read config"):
        AppConfig.load(tmp_path / "missing.yaml")
    broken = tmp_path / "broken.yaml"
    broken.write_text("factors: [unclosed\n", encoding="utf-8")
    with pytest.raises(UsageError, match="cannot parse config"):
        AppConfig.load(broken)
    broken_json = tmp_path / "broken.json"
    broken_json.write_text("{nope", encoding="utf-8")
    with pytest.raises(UsageError, match="cannot parse config"):
        AppConfig.load(broken_json)


def test_config_load_missing_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig.load()
    assert cfg.backend == "empirical_bayes"
    assert cfg.factor_enabled("team_bias") is True
    assert cfg.factor_enabled("cross_team_deps") is False
    assert cfg.factor_params("missing") == {}


def test_unknown_factor_name() -> None:
    with pytest.raises(KeyError):
        instantiate(FactorSpec(name="nope", enabled=True))


def test_ingest_unknown_adapter(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        ingest("not-an-adapter", {}, tmp_path / "db.sqlite")


def test_ingest_skips_and_dependencies(tmp_path: Path) -> None:
    class SkipAdapter:
        id = "skipper"
        display_name = "Skipper"

        def __init__(self, config: Mapping[str, Any]) -> None:
            self.config = dict(config)

        def test_connection(self) -> None:
            return None

        def fetch(self, query: Mapping[str, Any]) -> AdapterResult:
            created = datetime(2025, 1, 1, tzinfo=UTC)
            due = datetime(2026, 1, 1, tzinfo=UTC)
            done = datetime(2026, 1, 2, tzinfo=UTC)
            no_team = make_epic(external_id="NO-TEAM", team_id="t", slip_days=1)
            no_team = no_team.model_copy(update={"team_id": ""})
            no_due = make_epic(external_id="NO-DUE", team_id="t", slip_days=1, open_item=True)
            no_due = no_due.model_copy(update={"committed_deadline": None, "status": "done"})
            ok = Epic(
                tracker="mock",
                external_id="OK",
                team_id="t",
                status="done",
                committed_deadline=due,
                deadline_source="current_fallback",
                actual_completed_at=done,
                created_at=created,
                updated_at=done,
            )
            child = ChildIssue(
                tracker="mock",
                external_id="C1",
                epic_external_id="OK",
                status="open",
                updated_at=created,
            )
            dep = Dependency(
                tracker="mock",
                from_external_id="OK",
                to_external_id="X",
                from_kind="epic",
                to_team_id="other",
            )
            backwards = Epic(
                tracker="mock",
                external_id="BACKWARDS",
                team_id="t",
                status="done",
                committed_deadline=due,
                deadline_source="changelog",
                actual_completed_at=created,
                created_at=done,
                updated_at=done,
            )
            return AdapterResult(
                epics=[no_team, no_due, backwards, ok],
                children=[child],
                dependencies=[dep],
            )

    register_adapter("skipper", SkipAdapter)
    report = ingest("skipper", {}, tmp_path / "db.sqlite")
    assert report.skipped_unmapped_team == 1
    assert report.skipped_no_deadline == 1
    assert report.invalid == 1
    assert report.imported == 1
    assert report.updated == 0
    assert report.deadline_fallback == 1
    assert report.deadline_changelog == 0
    assert report.children_imported == 1
    assert [e["reason"] for e in report.errors] == [
        "skipped_unmapped_team",
        "skipped_no_deadline",
        "completed_before_created",
    ]


def test_cli_yaml_predict_and_errors(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    q = json.dumps({"seed": 3, "n_teams": 2, "n_epics": 40})
    assert main(["ingest", "--adapter", "mock", "--query", q, "--db", str(db)]) == 0
    assert main(["train", "--backend", "empirical_bayes", "--db", str(db)]) == 0
    yaml_path = tmp_path / "open.yaml"
    yaml_path.write_text(
        "- tracker: mock\n  external_id: Y1\n  team_id: team-0\n  status: open\n"
        "  committed_deadline: 2026-09-01T00:00:00+00:00\n  deadline_source: changelog\n"
        "  created_at: 2026-06-01T00:00:00+00:00\n  updated_at: 2026-06-01T00:00:00+00:00\n",
        encoding="utf-8",
    )
    assert main(["predict", "--file", str(yaml_path), "--status", "open", "--db", str(db)]) == 0
    assert main(["train", "--backend", "nope", "--db", str(tmp_path / "empty.sqlite")]) in {2, 4}
    assert main(["predict", "--status", "open", "--db", str(tmp_path / "nomodel.sqlite")]) == 5


def test_cli_usage_errors_exit_two(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    assert main(["ingest", "--adapter", "mock", "--query", "not-json", "--db", str(db)]) == 2
    assert main(["predict", "--file", str(tmp_path / "missing.json"), "--db", str(db)]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main(["predict", "--file", str(bad), "--db", str(db)]) == 2
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("epics: [unclosed\n", encoding="utf-8")
    assert main(["predict", "--file", str(bad_yaml), "--db", str(db)]) == 2
    scalar = tmp_path / "scalar.json"
    scalar.write_text('"just a string"', encoding="utf-8")
    assert main(["predict", "--file", str(scalar), "--db", str(db)]) == 2
    assert main(["predict", "--file", str(tmp_path), "--db", str(db)]) == 2
    with pytest.raises(SystemExit) as exc:
        main(["predict", "--status", "done", "--db", str(db)])
    assert exc.value.code == 2


def test_cli_empty_train(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    Store(db)
    assert main(["train", "--backend", "empirical_bayes", "--db", str(db)]) == 4


def test_store_unknown_model(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")
    with pytest.raises(NoActiveModelError):
        store.get_artifact()
    store.upsert_epics(two_team_history(n_per_team=1))
    art = store.save_artifact(
        backend="empirical_bayes",
        backend_version="1",
        factor_set_hash="x",
        quantiles=[0.5, 0.9],
        slip_unit="working_days",
        train_epic_count=1,
        train_team_count=1,
        data_cutoff=None,
        blob_path=str(tmp_path / "blob"),
        activate=False,
    )
    with pytest.raises(UsageError):
        store.get_artifact("missing-id")
    loaded = store.get_artifact(str(art.id))
    assert loaded.is_active is False


def test_predict_skips_undated_and_empty_train(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    with pytest.raises(EmptyTrainSetError):
        train("empirical_bayes", db)
    store.upsert_epics(two_team_history(n_per_team=8))
    cfg = AppConfig({"model": {"min_history": 3}, "factors": []})
    train("empirical_bayes", db, config=cfg)
    undated = make_epic(external_id="U", team_id="late-team", slip_days=0, open_item=True)
    undated = undated.model_copy(update={"committed_deadline": None, "deadline_source": None})
    assert predict(db, epics=[undated], config=cfg) == []


def test_empirical_bayes_empty_and_unfitted() -> None:
    backend = EmpiricalBayesBackend()
    frame = pd.DataFrame({"team_id": ["t"]})
    with pytest.raises(EmptyTrainSetError):
        backend.fit(frame.iloc[0:0], np.array([], dtype=float), {})
    with pytest.raises(UsageError):
        backend.predict_quantiles(frame)
    with pytest.raises(UsageError):
        backend.predict_on_time_proba(frame)


def test_jira_youtrack_auth_and_rich_fixtures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    monkeypatch.delenv("YOUTRACK_TOKEN", raising=False)
    with pytest.raises(AdapterAuthError):
        JiraAdapter({}).test_connection()
    with pytest.raises(AdapterAuthError):
        YouTrackAdapter({}).test_connection()
    with pytest.raises(AdapterAuthError):
        JiraAdapter({}).fetch({})
    with pytest.raises(AdapterAuthError):
        YouTrackAdapter({}).fetch({})

    jira_path = tmp_path / "jira.json"
    jira_path.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "key": "J-1",
                        "kind": "epic",
                        "fields": {
                            "summary": "Epic",
                            "issuetype": {"name": "Epic"},
                            "duedate": "2026-03-01",
                            "customfield_team": {"name": "alpha"},
                            "status": {"name": "Done"},
                            "resolutiondate": "2026-03-10T00:00:00Z",
                            "created": "2025-12-01T00:00:00",
                            "updated": "2026-03-10T00:00:00Z",
                            "issuelinks": [{"inwardIssue": {"key": "J-9"}}],
                        },
                        "due_changelog": [
                            {"at": "2025-12-01T00:00:00Z", "due": "2026-02-01T00:00:00Z"}
                        ],
                    },
                    {
                        "key": "J-2",
                        "fields": {
                            "issuetype": "Story",
                            "parent": {"key": "J-1"},
                            "status": "open",
                        },
                    },
                    {
                        "key": "J-SKIP",
                        "kind": "epic",
                        "fields": {"issuetype": {"name": "Epic"}, "status": {"name": "open"}},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    jira = JiraAdapter({"team_field": "customfield_team", "fixture_path": str(jira_path)})
    jira.test_connection()
    result = jira.fetch({})
    assert result.epics
    assert result.children
    assert result.dependencies

    yt_path = tmp_path / "yt.json"
    yt_path.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "idReadable": "Y-1",
                        "kind": "feature",
                        "fields": {
                            "type": "Feature",
                            "Team": {"name": "alpha"},
                            "due": "2026-03-01T00:00:00Z",
                            "created": "2025-12-01T00:00:00",
                        },
                        "links": [{"to_external_id": "Y-9", "to_team_id": "other"}],
                    },
                    {
                        "idReadable": "Y-2",
                        "fields": {"type": "Task", "parent": "Y-1"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    yt = YouTrackAdapter({"fixture_path": str(yt_path)})
    yt.test_connection()
    yt_result = yt.fetch({})
    assert yt_result.epics
    assert yt_result.children
    assert yt_result.dependencies


def test_ingest_skips_undated_fixture(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text(
        '{"epics":[{"external_id":"E","team_id":"t","status":"done",'
        '"created_at":"2025-01-01T00:00:00Z"}]}',
        encoding="utf-8",
    )
    result = MockAdapter({}).fetch({"fixture_path": str(path)})
    assert result.epics[0].committed_deadline is None

    db = tmp_path / "db.sqlite"
    report = ingest("mock", {"fixture_path": str(path)}, db)
    assert report.skipped_no_deadline == 1
    assert report.imported == 0
    assert Store(db).list_epics() == []


def test_vacations_and_holidays_missing_and_ctx(tmp_path: Path) -> None:
    assert load_vacations(None) == []
    assert load_holidays(tmp_path / "nope.yaml") == []
    vac = tmp_path / "v.yaml"
    vac.write_text(
        "vacations:\n  - team_id: t\n    start: 2026-01-01\n    end: 2026-01-02\n",
        encoding="utf-8",
    )
    assert load_vacations(vac)
    from predictability.factors.capacity_calendar import CapacityCalendarFactor

    factor = CapacityCalendarFactor({"vacations_path": str(vac)})
    ctx = FactorContext(
        vacations=[("t", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC), 0.0)]
    )
    factor.fit([], ctx)
    epic = make_epic(
        external_id="E",
        team_id="t",
        slip_days=0,
        open_item=True,
        deadline=datetime(2026, 1, 10, tzinfo=UTC),
        created=datetime(2026, 1, 1, tzinfo=UTC),
    )
    frame = factor.transform([epic], ctx)
    assert "vacation_overlap_days" in frame.columns


def test_cross_team_depth_and_child_team(caplog: pytest.LogCaptureFixture) -> None:
    epic = make_epic(external_id="E", team_id="t", slip_days=0, open_item=True)
    factor = CrossTeamDepsFactor({"max_depth": 0})
    ctx = FactorContext(
        children=[
            ChildIssue(
                tracker="mock",
                external_id="C",
                epic_external_id="E",
                status="open",
                team_id="other",
                updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
        dependencies=[
            Dependency(
                tracker="mock",
                from_external_id="E",
                to_external_id="X",
                from_kind="epic",
                to_team_id="foreign",
            )
        ],
    )
    with caplog.at_level(logging.WARNING):
        frame = factor.fit([epic], ctx).transform([epic], ctx)
    assert frame.loc["mock:E", "foreign_child_team_count"] == 1
    assert frame.loc["mock:E", "foreign_team_blocker_count"] == 1
    assert frame.loc["mock:E", "dep_depth"] == 0
    assert "max_depth=0" in caplog.text


def test_cross_team_deps_reports_reached_depth_and_survives_cycles() -> None:
    epic = make_epic(external_id="A", team_id="t", slip_days=0, open_item=True)
    chain = [
        Dependency(
            tracker="mock",
            from_external_id=src,
            to_external_id=dst,
            from_kind="epic",
            to_team_id=team,
        )
        for src, dst, team in [("A", "B", "b-team"), ("B", "C", "c-team"), ("C", "A", None)]
    ]
    ctx = FactorContext(dependencies=chain)
    frame = CrossTeamDepsFactor({"max_depth": 4}).transform([epic], ctx)
    assert frame.loc["mock:A", "dep_depth"] == 2
    assert frame.loc["mock:A", "foreign_team_blocker_count"] == 2

    shallow = CrossTeamDepsFactor({"max_depth": 1}).transform([epic], ctx)
    assert shallow.loc["mock:A", "dep_depth"] == 1


def test_cross_team_deps_empty_epics_keeps_columns() -> None:
    frame = CrossTeamDepsFactor().transform([], FactorContext())
    assert frame.empty
    assert "dep_depth" in frame.columns


def test_backend_lookup_falls_back_without_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_plugins(group: str, name: str) -> type:
        raise UsageError(f"no entry point {name}")

    monkeypatch.setattr("predictability.training.trainer.get_plugin", no_plugins)
    assert _backend_cls("empirical_bayes") is EmpiricalBayesBackend
    assert _backend_cls("quantile_catboost").name == "quantile_catboost"
    assert _backend_cls("quantile_lightgbm").name == "quantile_lightgbm"
    with pytest.raises(UsageError):
        _backend_cls("nope")


def test_build_results_skips_epics_without_a_deadline(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")
    artifact = store.save_artifact(
        backend="empirical_bayes",
        backend_version="1",
        factor_set_hash="x",
        quantiles=[0.5, 0.9],
        slip_unit="working_days",
        train_epic_count=1,
        train_team_count=1,
        data_cutoff=None,
        blob_path=str(tmp_path / "blob"),
        activate=True,
    )
    dated = make_epic(external_id="D", team_id="t", slip_days=0, open_item=True)
    undated = dated.model_copy(
        update={"external_id": "U", "committed_deadline": None, "deadline_source": None}
    )
    rows = build_results(
        [dated, undated],
        quantiles=np.array([[1.0, 2.0], [1.0, 2.0]]),
        on_time=np.array([0.5, 0.5]),
        artifact=artifact,
        team_history={"t": 3},
        min_history=5,
    )
    assert [r.external_id for r in rows] == ["D"]
    assert rows[0].cold_start is True
    assert rows[0].team_history_n == 3


def test_store_close_releases_engine(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")
    store.upsert_epics(two_team_history(n_per_team=1))
    store.close()
    assert store.list_epics() != []


def test_main_module_help(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.argv", ["predictability", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("predictability", run_name="__main__")
    assert exc.value.code == 0
