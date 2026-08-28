"""Estimate team work predictability from epic-level deadline slip.

Public library surface: ``ingest``, ``train``, ``predict``, ``evaluate``.
"""

from predictability.evaluation.backtest import evaluate
from predictability.ingest import ingest
from predictability.training.trainer import predict, train

__all__ = ["__version__", "evaluate", "ingest", "predict", "train"]

__version__ = "0.1.0"
