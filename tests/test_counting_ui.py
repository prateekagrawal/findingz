from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from findingz.hypotheses import AnalysisSample


@pytest.fixture
def counting_app(tmp_path, monkeypatch, request):
    library = {}
    for name, masses in [("signal", [85., 100.]), ("background", [85., 100.]),
                         ("other", [200., 300.])]:
        path = tmp_path / f"{name}.csv"
        pd.DataFrame({"mll": masses, "ptll": [0., 10.], "channel": ["ee", "mumu"],
                      "weight": [1., 1.]}).to_csv(path, index=False)
        library[name] = AnalysisSample(
            name, name, "generated", path, "test",
            {"collider_id": "lhc13", "beam_energy_gev": 6500., "run_mode": "madgraph"},
            generated_events=2, cross_section_pb=1.,
        )
    if getattr(request, "param", None) == "groups":
        for name in ["full-signal", "full-background"]:
            library[name] = replace(
                library["signal"], sample_id=name, label=name,
                config={**library["signal"].config, "run_mode": "full", "detector_id": "cms"},
            )
        library["missing-rate"] = replace(
            library["signal"], sample_id="missing-rate", label="missing-rate", cross_section_pb=None,
        )
    monkeypatch.setattr("findingz.hypotheses.build_sample_library", lambda *_: library)
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path))
    monkeypatch.setenv("FINDINGZ_VARIABLES_PATH", str(
        Path(__file__).parents[1] / "config/analysis_variables.yaml"
    ))
    return AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)


def _datasets(app):
    return next(widget for widget in app.multiselect if widget.label == "Datasets to plot")


def _cuts(app, kind):
    return next(widget for widget in app.multiselect
                if widget.key and widget.key.startswith(f"{kind}_cut_variables_"))


def _mass_slider(app, kind):
    return next(widget for widget in app.slider if widget.key.startswith(f"{kind}_cut_mll_"))


def _button(app, label):
    return next(widget for widget in app.button if widget.label == label)


def test_notebook_captures_current_selections(counting_app, tmp_path, monkeypatch):
    import json
    import matplotlib
    matplotlib.use("Agg", force=True)
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path / "notebooks"))
    app = counting_app
    app.multiselect(key="count_backgrounds").set_value(["background"]).run()
    _cuts(app, "count").set_value(["mll"]).run()
    _mass_slider(app, "count").set_value((90., 100.)).run()
    _button(app, "Save current analysis notebook").click().run()
    assert not app.exception
    doc = json.loads(Path(app.session_state["saved_analysis_notebook"]).read_text())
    namespace = {"display": lambda *_: None}
    for cell in doc["cells"]:
        if cell["cell_type"] == "code":
            exec(cell["source"], namespace)
    assert namespace["analysis"]["count"]["windows"]["mll"] == [90., 100.]
    assert namespace["analysis"]["plot"]["windows"] == {}
    assert namespace["result"].signal_yield == 500.


def test_counting_is_available_with_one_or_no_plotted_samples(counting_app):
    app = counting_app
    app.multiselect(key="count_backgrounds").set_value(["background"]).run()
    _datasets(app).set_value(["other"]).run()
    assert app.selectbox(key="count_signal").options == ["signal", "background", "other"]
    assert app.multiselect(key="count_backgrounds").options == ["background", "other"]
    _datasets(app).set_value([]).run()
    assert not app.exception
    assert _button(app, "Copy cuts from plot").disabled
    assert not _button(app, "Run cut-and-count").disabled
    _button(app, "Run cut-and-count").click().run()
    assert not app.error
    assert next(metric for metric in app.metric if metric.label == "Expected signal S").value == "1e+03"


def test_copy_is_explicit_exact_and_independent(counting_app):
    app = counting_app
    app.multiselect(key="count_backgrounds").set_value(["background"]).run()
    _datasets(app).set_value(["other"]).run()
    _cuts(app, "plot").set_value(["mll"]).run()
    _mass_slider(app, "plot").set_range(220., 280.).run()
    app.multiselect(key="analysis_channels").set_value(["mumu"]).run()
    assert not _cuts(app, "count").value
    _button(app, "Copy cuts from plot").click().run()
    assert not app.exception
    assert _mass_slider(app, "count").value == (220., 280.)
    # Counting samples only span 85–100 GeV; do not clamp the copied cut to that range.
    assert _mass_slider(app, "count").max >= 280.
    _mass_slider(app, "plot").set_range(230., 270.).run()
    app.multiselect(key="analysis_channels").set_value(["ee"]).run()
    assert _mass_slider(app, "count").value == (220., 280.)
    count_channels = next(widget for widget in app.multiselect
                          if widget.key and widget.key.startswith("count_channels_"))
    assert count_channels.value == ["mumu"]
    _button(app, "Run cut-and-count").click().run()
    assert not app.error
    assert next(metric for metric in app.metric if metric.label == "Expected signal S").value == "0"
    # Copying again replaces locally edited selections, even if plot cuts are unchanged.
    _cuts(app, "count").set_value([]).run()
    _button(app, "Copy cuts from plot").click().run()
    assert _mass_slider(app, "count").value == (230., 270.)
    _cuts(app, "count").set_value([]).run()
    _button(app, "Copy cuts from plot").click().run()
    assert _mass_slider(app, "count").value == (230., 270.)


def test_counting_roles_can_use_unplotted_sample(counting_app):
    app = counting_app
    _datasets(app).set_value(["signal"]).run()
    app.selectbox(key="count_signal").set_value("other").run()
    app.multiselect(key="count_backgrounds").set_value(["background"]).run()
    _button(app, "Run cut-and-count").click().run()
    assert not app.exception
    assert not app.error
    assert app.dataframe[-1].value["sample"].tolist() == ["other", "background"]


def test_unsupported_copy_leaves_counting_cuts_unchanged(counting_app, tmp_path):
    app = counting_app
    app.multiselect(key="count_backgrounds").set_value(["background"]).run()
    path = tmp_path / "background.csv"
    pd.read_csv(path).drop(columns="ptll").to_csv(path, index=False)
    _datasets(app).set_value(["other"]).run()
    _cuts(app, "count").set_value(["mll"]).run()
    _mass_slider(app, "count").set_range(90., 100.).run()
    _cuts(app, "plot").set_value(["ptll"]).run()
    _button(app, "Copy cuts from plot").click().run()
    assert not app.exception
    assert any("do not support ptll" in warning.value for warning in app.warning)
    assert _mass_slider(app, "count").value == (90., 100.)
    assert _cuts(app, "count").value == ["mll"]
    _datasets(app).set_value([]).run()
    assert _mass_slider(app, "count").value == (90., 100.)


def test_copying_empty_plot_selection_clears_counting_cuts(counting_app):
    app = counting_app
    app.multiselect(key="count_backgrounds").set_value(["background"]).run()
    _cuts(app, "count").set_value(["mll"]).run()
    _button(app, "Copy cuts from plot").click().run()
    assert not app.exception
    assert _cuts(app, "count").value == []


@pytest.mark.parametrize("counting_app", ["groups"], indirect=True)
def test_signal_filters_backgrounds_and_clears_only_incompatible_choices(counting_app):
    app = counting_app
    assert app.multiselect(key="count_backgrounds").options == ["background", "other"]
    app.multiselect(key="count_backgrounds").set_value(["background", "other"]).run()
    app.selectbox(key="count_signal").set_value("background").run()
    assert not app.exception
    assert app.multiselect(key="count_backgrounds").options == ["signal", "other"]
    assert app.multiselect(key="count_backgrounds").value == ["other"]
    assert any("Cleared backgrounds" in info.value for info in app.info)

    app.selectbox(key="count_signal").set_value("full-signal").run()
    assert not app.exception
    assert app.multiselect(key="count_backgrounds").options == ["full-background"]
    assert app.multiselect(key="count_backgrounds").value == []
    app.multiselect(key="count_backgrounds").set_value(["full-background"]).run()
    _button(app, "Run cut-and-count").click().run()
    assert not app.exception
    assert not app.error
    assert app.dataframe[-1].value["sample"].tolist() == ["full-signal", "full-background"]

    app.selectbox(key="count_signal").set_value("missing-rate").run()
    assert not app.exception
    assert app.multiselect(key="count_backgrounds").options == []
    assert app.multiselect(key="count_backgrounds").value == []
    assert app.multiselect(key="count_backgrounds").disabled
    assert any("cross-section normalization" in warning.value for warning in app.warning)


def test_empty_background_choice_stays_empty_on_rerun(counting_app):
    app = counting_app
    app.multiselect(key="count_backgrounds").set_value([]).run()
    app.run()
    assert not app.exception
    assert app.multiselect(key="count_backgrounds").value == []


def test_numbered_steps_start_without_an_automatic_background(counting_app):
    app = counting_app
    signal = app.selectbox(key="count_signal")
    assert signal.label == "1. Signal sample"
    assert app.multiselect(key="count_backgrounds").label == "2. Compatible background samples"
    assert app.multiselect(key="count_backgrounds").value == []
    assert not [button for button in app.button if button.label == "Run cut-and-count"]
    options = signal.options
    app.multiselect(key="count_backgrounds").set_value(["background"]).run()
    assert app.selectbox(key="count_signal").options == options
    assert app.selectbox(key="count_signal").value == "signal"
    app.multiselect(key="count_backgrounds").set_value([]).run()
    app.selectbox(key="count_signal").set_value("other").run()
    assert not app.exception
    assert app.multiselect(key="count_backgrounds").value == []
