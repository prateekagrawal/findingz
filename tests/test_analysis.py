import pandas as pd
import pytest

from findingz.analysis import execute_plan
from findingz.data import load_sample
from findingz.schemas import AnalysisFilter, AnalysisPlan


def test_analysis_executes_and_records_tools() -> None:
    plan = AnalysisPlan(
        samples=["signal", "background"],
        channels=["ee", "mumu"],
        filters=[AnalysisFilter(variable="min_lepton_pt", operator=">", value=20.0)],
        observable="mll",
        plot="overlay",
    )
    result = execute_plan(plan)
    assert result.summary.selected_events["signal"] > 0
    assert result.summary.selected_events["background"] > 0
    assert result.figure is not None
    names = [call.name for call in result.summary.tool_calls]
    assert "reconstruct_observable" in names
    assert "select_events" in names
    assert "make_plot" in names


def test_signal_is_concentrated_in_z_window() -> None:
    result = execute_plan(AnalysisPlan(samples=["signal"], plot="none"))
    selected = result.summary.selected_events["signal"]
    in_window = result.summary.z_window_counts["signal"]
    assert in_window / selected > 0.95


def test_loader_rejects_non_opposite_sign_pair(tmp_path) -> None:
    source = pd.read_csv("data/signal.csv").head(1)
    source.loc[:, "l2_charge"] = -1
    source.to_csv(tmp_path / "signal.csv", index=False)
    with pytest.raises(ValueError, match="opposite-sign same-flavor"):
        load_sample("signal", tmp_path)
