from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from predictability.adapters.base import AdapterResult, TrackerQuery
from predictability.core.schema import Epic
from predictability.ingest import ingest, register_adapter
from predictability.store.sqlite import Store
from predictability.training.trainer import predict, train


class StubAdapter:
    id = "stub"
    display_name = "Stub"

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = dict(config)

    def test_connection(self) -> None:
        return None

    def fetch(self, query: TrackerQuery) -> AdapterResult:
        epic = Epic(
            tracker="stub",
            external_id="S-1",
            team_id="stub-team",
            status="done",
            committed_deadline=datetime(2026, 2, 1, tzinfo=UTC),
            deadline_source="changelog",
            actual_completed_at=datetime(2026, 2, 8, tzinfo=UTC),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 2, 8, tzinfo=UTC),
        )
        open_e = epic.model_copy(
            update={
                "external_id": "S-OPEN",
                "status": "open",
                "actual_completed_at": None,
            }
        )
        # need enough history
        extras = [
            epic.model_copy(
                update={"external_id": f"S-{i}", "created_at": datetime(2025, 1, i + 1, tzinfo=UTC)}
            )
            for i in range(12)
        ]
        return AdapterResult(epics=[*extras, open_e])


def test_custom_adapter_ingest_train_predict(tmp_path: Path) -> None:
    register_adapter("stub", StubAdapter)
    db = tmp_path / "db.sqlite"
    ingest("stub", {}, db)
    store = Store(db)
    assert store.list_completed_epics()
    from predictability.core.config import AppConfig

    cfg = AppConfig({"model": {"min_history": 3}, "factors": []})
    train("empirical_bayes", db, config=cfg)
    results = predict(db, config=cfg)
    assert results
    assert results[0].backend == "empirical_bayes"
