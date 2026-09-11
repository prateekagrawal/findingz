import pytest
from pydantic import ValidationError

from findingz.models import ReplayBackend
from findingz.schemas import AnalysisFilter, AnalysisPlan


def test_between_filter_requires_two_ordered_values() -> None:
    with pytest.raises(ValidationError):
        AnalysisFilter(variable="mll", operator="between", value=[100.0, 80.0])


def test_unknown_filter_variable_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalysisFilter(variable="secret_label", operator=">", value=0.5)


def test_ambiguous_drell_yan_request_requires_clarification() -> None:
    plan = ReplayBackend().create_plan("Show me the Drell-Yan events.")
    assert not plan.execute
    assert plan.clarification


def test_replay_parses_common_comparison() -> None:
    plan = ReplayBackend().create_plan(
        "Compare signal and background in ee and mumu with pT above 20 GeV"
    )
    assert plan.execute
    assert plan.samples == ["signal", "background"]
    assert plan.channels == ["ee", "mumu"]
    assert plan.filters[0].variable == "min_lepton_pt"


def test_between_does_not_accidentally_select_ee_channel() -> None:
    plan = ReplayBackend().create_plan("Show collision data between 80 and 100 GeV")
    assert plan.channels == []


def test_non_executable_plan_requires_message() -> None:
    with pytest.raises(ValidationError):
        AnalysisPlan(execute=False)
