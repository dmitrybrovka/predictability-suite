"""CLI: ingest, train, predict, evaluate. No serve command."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

import yaml

from predictability.core.errors import PredictabilityError, UsageError
from predictability.core.schema import Epic, EvaluationReport
from predictability.evaluation.backtest import evaluate as run_evaluate
from predictability.ingest import ingest as run_ingest
from predictability.store.sqlite import DEFAULT_DB
from predictability.training.trainer import predict as run_predict
from predictability.training.trainer import train as run_train

EXIT_OK = 0


def _print_json(payload: Any, stream: TextIO = sys.stdout) -> None:
    data = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    stream.write(json.dumps(data, default=str))
    stream.write("\n")


def _load_epics(path: Path) -> list[Epic]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"cannot read --file {path}: {exc.strerror or exc}"
        raise UsageError(msg) from exc
    try:
        raw = yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
        items = raw if isinstance(raw, list) else raw.get("epics") or raw
        return [Epic.model_validate(item) for item in items]
    except (yaml.YAMLError, ValueError, AttributeError, TypeError) as exc:
        msg = f"cannot parse epics from {path}: {exc}"
        raise UsageError(msg) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="predictability")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--adapter", required=True)
    p_ing.add_argument("--query", default="{}")
    p_ing.add_argument("--db", type=Path, default=DEFAULT_DB)

    p_tr = sub.add_parser("train")
    p_tr.add_argument("--backend", required=True)
    p_tr.add_argument("--db", type=Path, default=DEFAULT_DB)
    p_tr.add_argument("--activate", action="store_true", default=True)
    p_tr.add_argument("--no-activate", action="store_false", dest="activate")

    p_pr = sub.add_parser("predict")
    p_pr.add_argument("--file", type=Path)
    p_pr.add_argument("--status", choices=["open"])
    p_pr.add_argument("--db", type=Path, default=DEFAULT_DB)
    p_pr.add_argument("--model-id")

    p_ev = sub.add_parser("evaluate")
    p_ev.add_argument("--backends", required=True)
    p_ev.add_argument("--db", type=Path, default=DEFAULT_DB)

    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if args.cmd == "ingest":
            try:
                query = json.loads(args.query)
            except json.JSONDecodeError as exc:
                msg = f"--query must be JSON: {exc}"
                raise UsageError(msg) from exc
            report = run_ingest(args.adapter, query, args.db)
            _print_json(report)
            print(
                f"imported={report.imported} updated={report.updated} skipped={report.skipped_no_deadline}",
                file=sys.stderr,
            )
            return EXIT_OK
        if args.cmd == "train":
            art = run_train(args.backend, args.db, activate=args.activate)
            _print_json(art)
            print(f"trained {art.backend} id={art.id} active={art.is_active}", file=sys.stderr)
            return EXIT_OK
        if args.cmd == "predict":
            file_epics = _load_epics(args.file) if args.file else None
            store_epics = None
            if args.status == "open" or (args.status is None and args.file is None):
                from predictability.store.sqlite import Store

                store_epics = Store(args.db).list_epics(status="open")
            if file_epics and store_epics:
                keys = {(e.tracker, e.external_id) for e in file_epics}
                merged = list(file_epics) + [
                    e for e in store_epics if (e.tracker, e.external_id) not in keys
                ]
            elif file_epics:
                merged = file_epics
            else:
                merged = store_epics or []
            results = run_predict(args.db, epics=merged, model_id=args.model_id)
            _print_json([r.model_dump(mode="json") for r in results])
            return EXIT_OK
        if args.cmd == "evaluate":
            names = [n.strip() for n in str(args.backends).split(",") if n.strip()]
            eval_report = run_evaluate(args.db, names)
            _print_json(eval_report)
            _print_eval_table(eval_report, sys.stderr)
            return EXIT_OK
        raise UsageError(f"unknown command {args.cmd}")
    except PredictabilityError as exc:
        print(json.dumps({"error": exc.message, "type": type(exc).__name__}), file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


def _print_eval_table(report: EvaluationReport, stream: TextIO) -> None:
    stream.write("backend\tmae\tpinball@0.9\tbrier\tn\terror\n")
    for row in report.rows:
        pb = row.pinball.get("0.9")
        stream.write(
            f"{row.backend}\t{row.mae_slip}\t{pb}\t{row.brier_on_time}\t{row.n_eval}\t{row.error or ''}\n"
        )


if __name__ == "__main__":
    raise SystemExit(main())
