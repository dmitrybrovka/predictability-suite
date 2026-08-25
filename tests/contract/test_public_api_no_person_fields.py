from predictability.core.schema import EvaluationReport, PredictabilityResult


def test_public_result_fields_have_no_person_keys() -> None:
    forbidden = {"person", "person_id", "assignee", "user", "rank", "person_slip"}
    result_fields = set(PredictabilityResult.model_fields)
    report_fields = set(EvaluationReport.model_fields)
    assert forbidden.isdisjoint(result_fields)
    assert forbidden.isdisjoint(report_fields)
    for name in result_fields:
        assert "person" not in name.lower()
