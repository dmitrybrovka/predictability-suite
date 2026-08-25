"""Plugin entry-point registry."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from predictability.core.errors import UsageError

ADAPTERS = "predictability.adapters"
FACTORS = "predictability.factors"
MODELS = "predictability.models"


def load_plugins(group: str) -> dict[str, Any]:
    selected = entry_points().select(group=group)
    return {ep.name: ep.load() for ep in selected}


def get_plugin(group: str, name: str) -> Any:
    plugins = load_plugins(group)
    if name not in plugins:
        msg = f"unknown {group} plugin {name!r}; known: {sorted(plugins)}"
        raise UsageError(msg)
    return plugins[name]
