from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from predictability.core.schema import (
    ChildIssue,
    Dependency,
    Epic,
    EvaluationReport,
    IngestReport,
    ModelArtifact,
    PredictabilityResult,
    Slip,
    Team,
)


def _epic(**kwargs: object) -> Epic:
    base = dict(
        tracker="mock",
        external_id="E-1",
        team_id="t1",
        status="done",
        committed_deadline=datetime(2026, 2, 1, tzinfo=UTC),
        deadline_source="changelog",
        actual_completed_at=datetime(2026, 2, 10, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 2, 10, tzinfo=UTC),
    )
    base.update(kwargs)
    return Epic.model_validate(base)


def test_epic_roundtrip() -> None:
    epic = _epic()
    assert epic.team_id == "t1"
    assert epic.model_dump()["status"] == "done"


def test_epic_rejects_person_field() -> None:
    with pytest.raises(ValidationError):
        _epic(person_id="alice")


def test_child_issue_not_prediction_object() -> None:
    child = ChildIssue(
        tracker="mock",
        external_id="C-1",
        epic_external_id="E-1",
        status="done",
        updated_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert child.epic_external_id == "E-1"


def test_dependency_and_team_and_slip() -> None:
    dep = Dependency(
        tracker="mock",
        from_external_id="E-1",
        to_external_id="E-2",
        from_kind="epic",
        to_team_id="other",
    )
    team = Team(team_id="t1")
    slip = Slip(tracker="mock", external_id="E-1", unit="working_days", value=3.0)
    assert dep.to_team_id == "other"
    assert team.active is True
    assert slip.value == 3.0


def test_ingest_report_and_artifact_and_result() -> None:
    report = IngestReport(imported=3)
    assert report.skipped_no_deadline == 0
    from uuid import uuid4

    art = ModelArtifact(
        id=uuid4(),
        backend="empirical_bayes",
        backend_version="1",
        factor_set_hash="abc",
        quantiles=[0.5, 0.9],
        slip_unit="working_days",
        train_epic_count=10,
        train_team_count=2,
        data_cutoff=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        blob_path="/tmp/x",
        is_active=True,
    )
    result = PredictabilityResult(
        tracker="mock",
        external_id="E-1",
        team_id="t1",
        committed_deadline=datetime(2026, 2, 1, tzinfo=UTC),
        deadline_source="changelog",
        expected_slip=2.0,
        quantiles={"0.5": 1.0, "0.9": 4.0},
        on_time_probability=0.4,
        cold_start=False,
        team_history_n=30,
        model_id=str(art.id),
        backend="empirical_bayes",
        factor_set_hash="abc",
    )
    assert "person" not in result.model_dump()
    assert EvaluationReport.model_fields["rows"]
