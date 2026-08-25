"""Synthetic completed-epic histories for tests and the mock adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from predictability.core.schema import ChildIssue, Dependency, Epic, EpicStatus


def make_epic(
    *,
    external_id: str,
    team_id: str,
    slip_days: int,
    tracker: str = "mock",
    status: EpicStatus = "done",
    created: datetime | None = None,
    deadline: datetime | None = None,
    open_item: bool = False,
) -> Epic:
    created_at = created or datetime(2025, 1, 1, tzinfo=UTC)
    committed = deadline or (created_at + timedelta(days=30))
    actual = None if open_item else committed + timedelta(days=slip_days)
    return Epic(
        tracker=tracker,
        external_id=external_id,
        team_id=team_id,
        status="open" if open_item else status,
        committed_deadline=committed,
        deadline_source="changelog",
        actual_completed_at=actual,
        created_at=created_at,
        updated_at=actual or committed,
        title=external_id,
    )


def two_team_history(
    *,
    n_per_team: int = 40,
    late_slip: int = 10,
    ontime_slip: int = 0,
    late_team: str = "late-team",
    ontime_team: str = "ontime-team",
) -> list[Epic]:
    epics: list[Epic] = []
    for i in range(n_per_team):
        epics.append(
            make_epic(
                external_id=f"LATE-{i}",
                team_id=late_team,
                slip_days=late_slip,
                created=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i),
            )
        )
        epics.append(
            make_epic(
                external_id=f"ON-{i}",
                team_id=ontime_team,
                slip_days=ontime_slip,
                created=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i),
            )
        )
    return epics


def generate_epics(
    *,
    seed: int = 42,
    n_teams: int = 3,
    n_epics: int = 120,
    include_open: int = 5,
) -> tuple[list[Epic], list[ChildIssue], list[Dependency]]:
    if n_epics <= 0 or n_teams <= 0:
        return [], [], []
    rng_mod = (seed % 7) - 3
    epics: list[Epic] = []
    children: list[ChildIssue] = []
    deps: list[Dependency] = []
    teams = [f"team-{i}" for i in range(n_teams)]
    per = max(1, n_epics // n_teams)
    idx = 0
    for t, team in enumerate(teams):
        bias = 8 if t == 0 else (0 if t == 1 else 3 + rng_mod)
        for _j in range(per):
            idx += 1
            eid = f"E-{idx}"
            created = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=idx)
            epics.append(
                make_epic(
                    external_id=eid,
                    team_id=team,
                    slip_days=bias,
                    created=created,
                )
            )
            cid = f"C-{idx}"
            children.append(
                ChildIssue(
                    tracker="mock",
                    external_id=cid,
                    epic_external_id=eid,
                    team_id=team,
                    status="done",
                    updated_at=created + timedelta(days=20),
                    actual_completed_at=created + timedelta(days=20),
                )
            )
            if t > 0 and idx % 4 == 0:
                deps.append(
                    Dependency(
                        tracker="mock",
                        from_external_id=eid,
                        to_external_id="E-1",
                        from_kind="epic",
                        to_team_id=teams[0],
                    )
                )
    done = epics[:n_epics]
    kept = {e.external_id for e in done}
    children = [c for c in children if c.epic_external_id in kept]
    deps = [d for d in deps if d.from_external_id in kept]
    opens: list[Epic] = []
    for k in range(include_open):
        idx += 1
        opens.append(
            make_epic(
                external_id=f"OPEN-{idx}",
                team_id=teams[k % n_teams],
                slip_days=0,
                created=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=k),
                open_item=True,
            )
        )
    return done + opens, children, deps


def open_epic(team_id: str, *, external_id: str = "OPEN-NEW") -> Epic:
    return make_epic(external_id=external_id, team_id=team_id, slip_days=0, open_item=True)
