from pathlib import Path

import pandas as pd
import pytest
import yaml
from streamlit.testing.v1 import AppTest

from findingz.hypotheses import AnalysisSample


@pytest.mark.parametrize("include_prepared", [False, True])
def test_plot_selector_allows_mixed_configurations(tmp_path, monkeypatch, include_prepared):
    path = tmp_path / "events.csv"
    pd.DataFrame({
        "channel": ["mumu", "ee"],
        "weight": [1.0, 1.0],
        "mll": [85.0, 100.0],
        "ptll": [10.0, 20.0],
        "rapidity_ll": [0.1, 0.2],
        "cos_theta_cs": [-0.2, 0.3],
        "l1_pt": [45.0, 50.0],
        "l2_pt": [40.0, 45.0],
        "l1_eta": [0.2, 0.1],
        "l2_eta": [-0.2, -0.1],
    }).to_csv(path, index=False)
    library = {
        name: AnalysisSample(
            sample_id=name, label=name, kind="generated", path=path,
            provenance="UI test", generated_events=2, cross_section_pb=1.0,
            config={"collider_id": name, "beam_energy_gev": energy},
        )
        for name, energy in [("LHC sample", 6500.0), ("LEP sample", 100.0)]
    }
    if include_prepared:
        library["prepared"] = AnalysisSample(
            sample_id="prepared", label="Teaching sample", kind="prepared",
            path=path, provenance="UI test", config={},
        )
    monkeypatch.setattr("findingz.hypotheses.build_sample_library", lambda *_: library)
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path))
    variable_path = tmp_path / "analysis_variables.yaml"
    variable_path.write_text(
        (Path(__file__).parents[1] / "config" / "analysis_variables.yaml").read_text()
    )
    monkeypatch.setenv("FINDINGZ_VARIABLES_PATH", str(variable_path))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    assert "Collider configuration" not in [widget.label for widget in app.selectbox]
    selector = next(widget for widget in app.multiselect if widget.label == "Datasets to plot")
    assert selector.options == [sample.menu_label for sample in library.values()]
    assert selector.value == list(library)
    assert not app.error
    assert app.dataframe[-1].value["sample"].tolist() == [s.label for s in library.values()]
    observable = app.selectbox(key="analysis_observable")
    plot_sliders = [slider for slider in app.slider if slider.key.startswith("plot_cut_")]
    count_sliders = [slider for slider in app.slider if slider.key.startswith("count_cut_")]
    assert not plot_sliders
    assert not count_sliders
    plot_cuts = next(widget for widget in app.multiselect
                     if widget.key and widget.key.startswith("plot_cut_variables_"))
    assert observable.options == plot_cuts.options
    assert app.multiselect(key="count_backgrounds").options == []
    assert app.multiselect(key="count_backgrounds").disabled
    assert not any("Soper" in label for label in observable.options)
    assert all(isinstance(slider.value, tuple) and len(slider.value) == 2
               for slider in plot_sliders)
    assert app.dataframe[-1].value["selected rows"].tolist() == [2] * len(library)

    # Signed eta cuts are real low/high selections, not an implicit |eta| bound.
    plot_cuts.set_value(["leading_lepton_eta"]).run()
    eta = next(slider for slider in app.slider
               if slider.key.startswith("plot_cut_leading_lepton_eta_"))
    eta.set_range(0.1, 0.1).run()
    assert not app.exception
    assert not app.error
    assert app.dataframe[-1].value["selected rows"].tolist() == [1] * len(library)
    assert not [slider for slider in app.slider if slider.key.startswith("count_cut_")]

    normalization = next(widget for widget in app.radio if widget.label == "Plot normalization")
    normalization.set_value("Expected yields").run()
    assert not app.exception
    assert not app.error
    assert app.dataframe[-1].value["sample"].tolist() == [s.label for s in library.values()]

    assert not [button for button in app.button if button.label == "Run cut-and-count"]
    assert not app.exception
    assert any("No compatible background" in info.value for info in app.info)

    # Removing a selected variable must remove the cut as well as its slider.
    next(widget for widget in app.multiselect
         if widget.key and widget.key.startswith("plot_cut_variables_")).set_value([]).run()
    assert not app.exception
    assert not [slider for slider in app.slider if slider.key.startswith("plot_cut_")]
    assert app.dataframe[-1].value["selected rows"].tolist() == [2] * len(library)

    # Reload in the same live session: no code reload, rebuild, or cached definitions.
    payload = yaml.safe_load(variable_path.read_text())
    payload["default_variables"] = ["mll"]
    payload["variables"]["mll"]["label"] = "Pair mass [GeV]"
    variable_path.write_text(yaml.safe_dump(payload))
    app.run()
    assert not app.exception
    assert not app.error
    assert app.selectbox(key="analysis_observable").options == ["Pair mass [GeV]"]
    assert not [slider for slider in app.slider if slider.key.startswith("plot_cut_")]
    cuts = next(widget for widget in app.multiselect
                if widget.key and widget.key.startswith("plot_cut_variables_"))
    assert cuts.options == ["Pair mass [GeV]"]
    cuts.set_value(["mll"]).run()
    assert [slider.label for slider in app.slider if slider.key.startswith("plot_cut_")] == [
        "Pair mass [GeV]"
    ]
