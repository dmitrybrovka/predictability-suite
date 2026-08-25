"""YAML/JSON configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from predictability.core.errors import UsageError
from predictability.core.schema import DEFAULT_MIN_HISTORY, FactorSpec, SlipUnit


def _read(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"cannot read config {path}: {exc.strerror or exc}"
        raise UsageError(msg) from exc
    try:
        loaded = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (yaml.YAMLError, ValueError) as exc:
        msg = f"cannot parse config {path}: {exc}"
        raise UsageError(msg) from exc
    if not isinstance(loaded, dict):
        msg = f"config root must be a mapping: {path}"
        raise UsageError(msg)
    return loaded


class AppConfig:
    def __init__(self, raw: dict[str, Any], *, source: Path | None = None) -> None:
        self.raw = raw
        self.source = source
        slip = raw.get("slip") or {}
        model = raw.get("model") or {}
        self.slip_unit: SlipUnit = slip.get("unit", "working_days")
        self.timezone: str = slip.get("timezone", "UTC")
        self.weekend: list[int] = list(slip.get("weekend") or [5, 6])
        self.backend: str = model.get("backend", "empirical_bayes")
        self.min_history: int = int(model.get("min_history", DEFAULT_MIN_HISTORY))
        self.shrinkage_k: float = float(model.get("shrinkage_k", 10))
        self.quantiles: tuple[float, ...] = tuple(model.get("quantiles") or [0.5, 0.9])
        self.factors: list[FactorSpec] = [
            FactorSpec.model_validate(item) for item in (raw.get("factors") or [])
        ]
        self.adapters: dict[str, Any] = dict(raw.get("adapters") or {})

    @classmethod
    def load(cls, path: Path | None = None) -> AppConfig:
        if path is None:
            default = Path("config/default.yaml")
            if default.is_file():
                path = default
            else:
                return cls({})
        return cls(_read(path), source=path)

    @property
    def holidays_path(self) -> Path | None:
        """Org holiday file: `slip.holidays_path`, else the capacity factor's path."""
        slip = self.raw.get("slip") or {}
        raw_path = slip.get("holidays_path") or self.factor_params("capacity_calendar").get(
            "holidays_path"
        )
        return Path(str(raw_path)) if raw_path else None

    def factor_params(self, name: str) -> dict[str, Any]:
        for spec in self.factors:
            if spec.name == name:
                return spec.params
        return {}

    def factor_enabled(self, name: str) -> bool:
        for spec in self.factors:
            if spec.name == name:
                return spec.enabled
        return name == "team_bias"
