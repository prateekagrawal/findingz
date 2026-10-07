import pytest
from streamlit.testing.v1 import AppTest

from findingz.hep_pipeline import HepSimulationConfig, _pipeline_hash
from findingz.param_card import ParamCardOptions, apply_overrides, parse_edits


CARD = """# model
BLOCK MASS
 23 9.1188e1 # MZ
BLOCK NMIX Q= 1e3
 1 2 0.0 # mixing
DECAY 23 2.4 # WZ
 0.5 2 11 -11 # branching fraction
DECAY 24 2.0
"""


def test_slha_edits_preserve_other_parameters_and_branching_fractions():
    options = ParamCardOptions(defaults={"mass 23": 91.2}, editable=["decay 23", "nmix 1 2"])
    values = parse_edits("2.5 = decay 23\n1.2d-1 = nmix 1 2", options)
    edited = apply_overrides(CARD, values)
    assert "23  91.2 # MZ" in edited
    assert "DECAY  23  2.5 # WZ" in edited
    assert "1  2  0.12 # mixing" in edited
    assert "0.5 2 11 -11 # branching fraction" in edited
    assert "DECAY 24 2.0" in edited
    with pytest.raises(ValueError, match="absent"):
        apply_overrides(CARD, {"mass 999": 1})
    with pytest.raises(ValueError, match="dependent"):
        apply_overrides("BLOCK MASS\n# Dependent parameters\n24 80.4\n", {"mass 24": 81})


@pytest.mark.parametrize("text", ["nan = mass 23", "True = mass 23", "Auto = decay 23",
                                   "-1 = decay 23", "2 = mass 23\n3 = mass 23", "1 = mass 24"])
def test_bad_parameter_edits_fail(text):
    with pytest.raises(ValueError):
        parse_edits(text, ParamCardOptions(editable=["mass 23", "decay 23"]))


def test_parameter_changes_make_new_run_identity():
    first = HepSimulationConfig(run_mode="madgraph")
    second = HepSimulationConfig(run_mode="madgraph", param_card_overrides={"mass 23": 92})
    assert _pipeline_hash(first, "test") != _pipeline_hash(second, "test")
    for value in [True, float("inf"), "Auto"]:
        with pytest.raises(ValueError):
            HepSimulationConfig(param_card_overrides={"decay 23": value})


def test_parameter_editor():
    app = AppTest.from_string('''
import streamlit as st
from findingz.ui import _render_param_card_editor
from findingz.param_card import ParamCardOptions
st.session_state["params"] = _render_param_card_editor(
    ParamCardOptions(editable=["mass 23", "decay 23"]), "test",
    lambda: {"mass 23": "91.188", "decay 23": "2.495"})
''', default_timeout=30).run()
    assert not app.exception
    assert app.session_state["params"] == {}
    next(b for b in app.button if b.label == "mass 23").click().run()
    app.number_input[0].set_value(92.0).run()
    assert app.session_state["params"] == {"mass 23": 92.0}
    next(b for b in app.button if b.label == "mass 23").click().run()
    next(b for b in app.button if b.label == "decay 23").click().run()
    app.number_input[0].set_value(-1.0).run()
    assert app.session_state["params"] is None
