import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from predictability.core.schema import DEFAULT_MIN_HISTORY, ChildIssue, Dependency
from predictability.core.synthetic import make_epic, two_team_history
from predictability.store.sqlite import Store


def test_upsert_and_uniqueness(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    epics = two_team_history(n_per_team=2)
    r1 = store.upsert_epics(epics)
    r2 = store.upsert_epics(epics)
    assert r1.imported == 4
    assert r2.updated == 4
    assert r2.imported == 0
    assert len(store.list_completed_epics()) == 4


def test_children_deps_artifacts(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    store = Store(db)
    epic = make_epic(external_id="E-1", team_id="t", slip_days=1)
    store.upsert_epics([epic])
    n = store.upsert_children(
        [
            ChildIssue(
                tracker="mock",
                external_id="C-1",
                epic_external_id="E-1",
                status="done",
                updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]
    )
    assert n == 1
    store.replace_dependencies(
        "mock",
        [
            Dependency(
                tracker="mock",
                from_external_id="E-1",
                to_external_id="E-2",
                from_kind="epic",
                to_team_id="other",
            )
        ],
    )
    assert len(store.list_dependencies()) == 1
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
        activate=True,
    )
    assert store.get_artifact().id == art.id
    art2 = store.save_artifact(
        backend="empirical_bayes",
        backend_version="1",
        factor_set_hash="x",
        quantiles=[0.5, 0.9],
        slip_unit="working_days",
        train_epic_count=2,
        train_team_count=1,
        data_cutoff=None,
        blob_path=str(tmp_path / "blob2"),
        activate=True,
    )
    assert store.get_artifact().id == art2.id
    assert store.get_artifact(art.id).is_active is False


def _artifact(store: Store, tmp_path: Path, *, min_history: int) -> str:
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
        activate=True,
        min_history=min_history,
    )
    return str(art.id)


def test_min_history_round_trips(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite")
    art_id = _artifact(store, tmp_path, min_history=7)
    assert store.get_artifact(art_id).min_history == 7


def test_opens_database_written_before_min_history_column(tmp_path: Path) -> None:
    """`create_all` never alters existing tables, so an older database has to be
    patched on open instead of failing every artifact read."""
    db = tmp_path / "legacy.sqlite"
    store = Store(db)
    art_id = _artifact(store, tmp_path, min_history=7)
    store.close()
    conn = sqlite3.connect(db)
    try:
        conn.execute("ALTER TABLE artifacts DROP COLUMN min_history")
        conn.commit()
    finally:
        conn.close()

    reopened = Store(db)
    assert reopened.get_artifact(art_id).min_history == DEFAULT_MIN_HISTORY
    assert str(reopened.get_artifact().id) == art_id
    fresh = _artifact(reopened, tmp_path, min_history=3)
    assert reopened.get_artifact(fresh).min_history == 3
