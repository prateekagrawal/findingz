from pathlib import Path

import pandas as pd
import pytest

from findingz.analysis_variables import (
    AnalysisVariable,
    VariableCatalog,
    apply_windows,
    load_variable_catalog,
    slider_bounds,
)
from findingz.hypotheses import AnalysisSample


def test_process_tables_use_intersection_and_existing_columns():
    catalog = load_variable_catalog(Path(__file__).parents[1] / "config/analysis_variables.yaml")
    catalog.processes["custom"] = ["mll", "leading_lepton_eta", "ptll"]
    samples = [
        AnalysisSample(name, name, "generated", Path("unused.csv"), "test", {"process": process})
        for name, process in [("a", "dy_ll"), ("b", "custom")]
    ]
    frames = {
        "a": pd.DataFrame({"mll": [90], "leading_lepton_eta": [0.2], "ptll": [0]}),
        "b": pd.DataFrame({"mll": [90], "leading_lepton_eta": [0.2]}),
    }
    assert list(catalog.available(samples, frames)) == ["mll", "leading_lepton_eta"]
    catalog.variables["leading_lepton_eta"].enabled = False
    assert list(catalog.available(samples, frames)) == ["mll"]


@pytest.mark.parametrize("names", [["missing"], ["mll", "mll"]])
def test_catalog_rejects_invalid_variable_lists(names):
    with pytest.raises(ValueError):
        VariableCatalog(variables={}, default_variables=names)


def test_range_and_selection_use_configured_column_and_both_edges():
    variable = AnalysisVariable(column="x", label="Example", description="Test", step=0.1)
    frame = pd.DataFrame({"x": [-0.25, 0.0, 0.15, 0.35, float("nan")]})
    bounds = slider_bounds([frame], variable)
    assert bounds == pytest.approx((-0.3, 0.4))
    selected = apply_windows(frame, {"renamed": (0.0, 0.2)}, {"renamed": variable})
    assert selected["x"].tolist() == [0.0, 0.15]
    assert slider_bounds([pd.DataFrame({"x": [0.0]})], variable) == (0.0, 0.1)
    assert slider_bounds([pd.DataFrame({"x": [float("nan")]})], variable) == (0.0, 0.1)


def test_bad_live_catalog_does_not_silently_fall_back(tmp_path):
    path = tmp_path / "variables.yaml"
    path.write_text("schema_version: 99\n")
    with pytest.raises(ValueError):
        load_variable_catalog(path)
