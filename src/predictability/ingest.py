"""Ingest adapter output into SQLite."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from predictability.adapters.base import TrackerQuery
from predictability.adapters.jira import JiraAdapter
from predictability.adapters.mock import MockAdapter
from predictability.adapters.youtrack import YouTrackAdapter
from predictability.core.config import AppConfig
from predictability.core.errors import UsageError
from predictability.core.registry import ADAPTERS, get_plugin
from predictability.core.schema import IngestReport
from predictability.store.sqlite import Store

_ADAPTERS: dict[str, type] = {
    "mock": MockAdapter,
    "jira": JiraAdapter,
    "youtrack": YouTrackAdapter,
}


def register_adapter(name: str, cls: type) -> None:
    """Register an in-process adapter fallback used when entry points are missing."""
    _ADAPTERS[name] = cls


def _adapter(name: str, config: Mapping[str, Any]) -> Any:
    try:
        cls = get_plugin(ADAPTERS, name)
    except UsageError:
        cls = _ADAPTERS.get(name)
    if cls is None:
        raise UsageError(f"unknown adapter {name}")
    return cls(config)


_ERROR_SAMPLE = 10


def _note(report: IngestReport, reason: str, external_id: str) -> None:
    if len(report.errors) < _ERROR_SAMPLE:
        report.errors.append({"reason": reason, "external_id": external_id})


def ingest(
    adapter: str,
    query: TrackerQuery | Mapping[str, Any],
    db: Path | str,
    *,
    config: AppConfig | None = None,
) -> IngestReport:
    """Fetch from ``adapter``, skip unmapped/no-deadline rows, and upsert SQLite.

    Args:
        adapter: Registry name (``mock``, ``jira``, ``youtrack``, or a plugin).
        query: Adapter query (JQL, fixture path, mock seed, …).
        db: SQLite path.
        config: App config; adapter settings are read from ``adapters.<name>``.

    Returns:
        Import/update/skip counts. Dependencies for this tracker are replaced.

    Raises:
        UsageError: Unknown adapter name.
        AdapterError: Connection or fetch failed.
    """
    cfg = config or AppConfig.load()
    adapter_cfg = dict(cfg.adapters.get(adapter) or {})
    inst = _adapter(adapter, adapter_cfg)
    inst.test_connection()
    result = inst.fetch(dict(query))
    store = Store(db)
    accepted = []
    report = IngestReport()
    for epic in result.epics:
        if not epic.team_id:
            _note(report, "skipped_unmapped_team", epic.external_id)
            report.skipped_unmapped_team += 1
            continue
        if epic.committed_deadline is None:
            _note(report, "skipped_no_deadline", epic.external_id)
            report.skipped_no_deadline += 1
            continue
        if epic.actual_completed_at is not None and epic.actual_completed_at < epic.created_at:
            _note(report, "completed_before_created", epic.external_id)
            report.invalid += 1
            continue
        if epic.deadline_source == "changelog":
            report.deadline_changelog += 1
        elif epic.deadline_source == "current_fallback":
            report.deadline_fallback += 1
        accepted.append(epic)
    upsert = store.upsert_epics(accepted)
    report.imported = upsert.imported
    report.updated = upsert.updated
    report.children_imported = store.upsert_children(list(result.children))
    owned = {adapter}
    adapter_id = getattr(inst, "id", None)
    if isinstance(adapter_id, str) and adapter_id:
        owned.add(adapter_id)
    owned.update(e.tracker for e in result.epics)
    owned.update(c.tracker for c in result.children)
    owned.update(d.tracker for d in result.dependencies)
    store.replace_dependencies(owned, list(result.dependencies))
    return report
