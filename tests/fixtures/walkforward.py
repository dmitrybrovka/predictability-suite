from predictability.core.schema import Epic
from predictability.core.synthetic import generate_epics


def large_history(*, n: int = 1000) -> list[Epic]:
    epics, _c, _d = generate_epics(seed=99, n_teams=4, n_epics=n, include_open=0)
    return epics
