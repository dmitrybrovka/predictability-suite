import json
from pathlib import Path

import pytest

from predictability.cli import main
from predictability.core.synthetic import open_epic
from predictability.store.sqlite import Store
from predictability.training.trainer import predict as lib_predict


def test_cli_no_serve_and_unknown_backend(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "db.sqlite"
    q = json.dumps({"seed": 1, "n_teams": 2, "n_epics": 30})
    assert main(["ingest", "--adapter", "mock", "--query", q, "--db", str(db)]) == 0
    capsys.readouterr()
    code = main(["train", "--backend", "nope", "--db", str(db)])
    captured = capsys.readouterr()
    assert code == 2
    assert "Traceback" not in captured.out
    from predictability import cli as cli_mod

    parser_src = Path(cli_mod.__file__).read_text(encoding="utf-8")
    assert 'add_parser("serve")' not in parser_src


def test_cli_ingest_train_predict_evaluate(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    q = json.dumps({"seed": 1, "n_teams": 2, "n_epics": 80})
    assert main(["ingest", "--adapter", "mock", "--query", q, "--db", str(db)]) == 0
    assert main(["train", "--backend", "empirical_bayes", "--db", str(db)]) == 0
    store = Store(db)
    sample = store.list_epics(status="open")[:1]
    if not sample:
        sample = [open_epic("team-0", external_id="F1")]
        store.upsert_epics(sample)
    open_path = tmp_path / "open.json"
    open_path.write_text(json.dumps([sample[0].model_dump(mode="json")]), encoding="utf-8")
    assert main(["predict", "--file", str(open_path), "--db", str(db)]) == 0
    rows = lib_predict(db, epics=sample)
    assert rows[0].backend == "empirical_bayes"
    active = store.active_id()
    assert main(["evaluate", "--backends", "empirical_bayes", "--db", str(db)]) == 0
    assert Store(db).active_id() == active
    assert main(["predict", "--status", "open", "--db", str(db)]) == 0
