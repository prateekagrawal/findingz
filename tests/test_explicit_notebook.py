import json
from pathlib import Path

import pandas as pd
import pytest

from findingz.hypotheses import AnalysisSample
from findingz.notebook_analysis import compare_samples
from findingz.notebook_export import save_notebook


@pytest.mark.parametrize("uncertainty", [0.0, 0.1])
def test_explicit_export_matches_helper(tmp_path, monkeypatch, uncertainty):
    library = {}
    for key, cross_section in [("null", 29.), ("alternative", 656.)]:
        path = tmp_path / f"{key}.csv"
        pd.DataFrame({"mll": [70., 90., 100.], "channel": ["ee", "ee", "mumu"],
                      "weight": [1., 2., 1.]}).to_csv(path, index=False)
        library[key] = AnalysisSample(key, key, "generated", path, "fixture",
                                     {"run_mode": "madgraph"}, 1000, cross_section)
    monkeypatch.setattr("findingz.notebook_analysis.available_samples", lambda: library)
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    monkeypatch.delenv("FINDINGZ_NOTEBOOK_TEMPLATE", raising=False)
    variables = {"mass": {"column": "mll", "label": "Mass [GeV]", "step": 1.0,
                          "description": "Saved alias"}}
    settings = {"plot": {"samples": list(library), "observable": "mass", "windows": {},
                         "variables": variables, "expected_yields": True, "luminosity_fb": 2e-5},
                "count": {"mode": "hypothesis_comparison", "null": "null", "alternative": "alternative",
                          "windows": {"mass": [80., 100.]}, "channels": ["ee"], "variables": variables,
                          "luminosity_fb": 2e-5, "null_uncertainty_fraction": uncertainty}}
    notebook = json.loads(save_notebook("explicit", settings).read_text())
    namespace = {"display": lambda *_: None}
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert "compare_samples(" not in cell["source"]
            assert "comparison_table(" not in cell["source"]
            exec(cell["source"], namespace)
    expected = compare_samples(library, "null", "alternative", cuts={"mass": (80., 100.)},
                               channels=["ee"], luminosity_fb=2e-5,
                               null_uncertainty=uncertainty, variables=variables)
    assert namespace["n0"] == pytest.approx(expected.null_yield)
    assert namespace["n1"] == pytest.approx(expected.alternative_yield)
    assert namespace["z_expected"] == pytest.approx(expected.signed_significance)
    assert "Optional extension" not in json.dumps(notebook)
    assert namespace["plot_weights"]["null"].sum() == pytest.approx(4 * 29 * 2e-5 * 1000 / 1000)
