"""Estimate team work predictability from epic-level deadline slip."""

from predictability.evaluation.backtest import evaluate
from predictability.ingest import ingest
from predictability.training.trainer import predict, train

__all__ = ["__version__", "evaluate", "ingest", "predict", "train"]

__version__ = "0.1.0"
