from collections.abc import Mapping
from pathlib import Path
from typing import Any

from predictability.adapters.base import AdapterResult
from predictability.core.schema import Dependency
from predictability.core.synthetic import make_epic
from predictability.ingest import ingest, register_adapter
from predictability.store.sqlite import Store


def test_reingest_does_not_grow_rows(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    q = {"seed": 3, "n_teams": 2, "n_epics": 40}
    first = ingest("mock", q, db)
    n1 = Store(db).train_row_count()
    deps1 = len(Store(db).list_dependencies())
    second = ingest("mock", q, db)
    n2 = Store(db).train_row_count()
    assert n1 > 0
    assert n2 == n1
    assert deps1 > 0
    assert len(Store(db).list_dependencies()) == deps1
    assert first.imported > 0
    assert second.imported == 0
    assert second.updated == first.imported


def test_reingest_dedupes_when_adapter_name_differs_from_tracker(tmp_path: Path) -> None:
    """Deps are keyed by the tracker on the row, not by the adapter that fetched
    them; a mismatch used to duplicate every link on each re-ingest."""

    class RenamedAdapter:
        id = "corp-jira"
        display_name = "Corp Jira"

        def __init__(self, config: Mapping[str, Any]) -> None:
            self.config = dict(config)

        def test_connection(self) -> None:
            return None

        def fetch(self, query: Mapping[str, Any]) -> AdapterResult:
            epic = make_epic(external_id="E-1", team_id="t", slip_days=1, tracker="jira")
            dep = Dependency(
                tracker="jira",
                from_external_id="E-1",
                to_external_id="E-2",
                from_kind="epic",
                to_team_id="other",
            )
            return AdapterResult(epics=[epic], dependencies=[dep])

    register_adapter("corp-jira", RenamedAdapter)
    db = tmp_path / "renamed.sqlite"
    ingest("corp-jira", {}, db)
    ingest("corp-jira", {}, db)
    assert len(Store(db).list_dependencies()) == 1


def test_reingest_with_no_links_clears_previous_dependencies(tmp_path: Path) -> None:
    class ToggleAdapter:
        id = "corp-jira"
        display_name = "Corp Jira"
        emit_dep = True

        def __init__(self, config: Mapping[str, Any]) -> None:
            self.config = dict(config)

        def test_connection(self) -> None:
            return None

        def fetch(self, query: Mapping[str, Any]) -> AdapterResult:
            epic = make_epic(external_id="E-1", team_id="t", slip_days=1, tracker="jira")
            deps = []
            if self.emit_dep:
                deps.append(
                    Dependency(
                        tracker="jira",
                        from_external_id="E-1",
                        to_external_id="E-2",
                        from_kind="epic",
                        to_team_id="other",
                    )
                )
            return AdapterResult(epics=[epic], dependencies=deps)

    register_adapter("corp-jira-toggle", ToggleAdapter)
    db = tmp_path / "toggle.sqlite"
    ingest("corp-jira-toggle", {}, db)
    assert len(Store(db).list_dependencies()) == 1
    ToggleAdapter.emit_dep = False
    ingest("corp-jira-toggle", {}, db)
    assert Store(db).list_dependencies() == []
