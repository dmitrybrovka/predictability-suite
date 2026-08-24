# Tracker adapter protocol

**Feature**: `001-team-work-predictability`  
**Consumers**: ingest CLI, library ingest, contract tests  
**Canonical output**: [Epic](../data-model.md#epic) + [ChildIssue](../data-model.md#childissue)

v1 has **no** `POST /ingest`. HTTP is v2.

## Purpose

Map a task-tracker API (or fixture) into canonical epics, children, and dependencies. Factors and models MUST NOT import adapter modules.

## Registration

Entry point group: `predictability.adapters`

```text
[project.entry-points."predictability.adapters"]
jira = "predictability.adapters.jira:JiraAdapter"
youtrack = "predictability.adapters.youtrack:YouTrackAdapter"
mock = "predictability.adapters.mock:MockAdapter"
```

## Interface

```python
class TrackerQuery(TypedDict, total=False):
    jql: str
    youtrack_query: str
    project: str
    updated_since: str
    fixture_path: str

class AdapterResult:
    epics: Iterator[Epic]
    children: Iterator[ChildIssue]
    dependencies: Iterator[Dependency]

class TrackerAdapter(Protocol):
    id: str
    display_name: str

    def __init__(self, config: Mapping[str, Any]) -> None: ...

    def test_connection(self) -> None:
        """Raise AdapterAuthError / AdapterTransientError."""

    def fetch(self, query: TrackerQuery) -> AdapterResult:
        """Yield canonical epics (filtered by configured epic types),
        their children, and links. Changelog MUST be applied when available."""
```

Adapters MAY split `fetch` into `fetch_epics` / `fetch_children` / `fetch_links` as long as ingest sees the same three streams.

## Required config (built-ins)

Shared:

| Key | Meaning |
|-----|---------|
| `team_field` | Explicit map to `team_id` (required) |
| `epic_issue_types` | List of types/tags treated as epics |
| `epic_done` | `own` \| `children` \| `own_then_children` (default `own_then_children`) |
| `due_field` | Due/target field name |

### Jira

| Key | Meaning |
|-----|---------|
| `base_url` | |
| token via `JIRA_TOKEN` | Prefer env over plaintext |
| changelog | **Required capability**; expand changelog for due field history |

### YouTrack

| Key | Meaning |
|-----|---------|
| `base_url` | |
| `YOUTRACK_TOKEN` | |
| activity/changelog | **Required capability** for first due date |

### Mock

| Key | Meaning |
|-----|---------|
| `fixture_path` | JSON with epics, children, optional `due_changelog` |
| `seed` | synthetic generator |

## Deadline mapping

1. Walk due-field changelog (oldest first); first non-null due date → `committed_deadline`, `deadline_source=changelog`.
2. If history missing or unreadable for that item → current due, `deadline_source=current_fallback`.
3. If still no due → ingest skips the epic.

Auth failure on changelog **endpoint** is a run-level error. Per-item missing history is fallback, not skip (unless no current due either).

## Completion mapping

Apply `epic_done`:

- `own`: epic resolution/Done timestamp only
- `children`: timestamp when all children are Done (or last child completion — document in adapter)
- `own_then_children`: own if present, else children rule

## Contract tests

1. Fixture with two due-date changelog entries → `committed_deadline` equals the **first**, `deadline_source=changelog`.
2. Fixture without changelog → current due + `current_fallback`.
3. YouTrack and Jira fixtures produce the same canonical field set.
4. Child `external_id`s never appear as Epic rows in the store after ingest.
5. Missing `team_field` mapping → skip + ingest counter, not a crash.
6. `fetch` on empty query/fixture does not raise.
