import json
from pathlib import Path

import pytest

from predictability.cli import main
from predictability.store.sqlite import Store


def test_cli_flow_mock_ingest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "flow.sqlite"
    q = json.dumps({"seed": 42, "n_teams": 3, "n_epics": 90})
    assert main(["ingest", "--adapter", "mock", "--query", q, "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["train", "--backend", "empirical_bayes", "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["predict", "--status", "open", "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["evaluate", "--backends", "empirical_bayes", "--db", str(db)]) == 0
    store = Store(db)
    assert store.train_row_count() >= 10
