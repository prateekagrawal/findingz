import pytest
from streamlit.testing.v1 import AppTest


def test_luminosity_units_preserve_exposure_and_convert_small_values():
    app = AppTest.from_string('''
import streamlit as st
from findingz.ui import _luminosity_input
st.session_state["result_fb"] = _luminosity_input("test_lumi")
''', default_timeout=30).run()
    assert not app.exception
    assert app.selectbox(key="test_lumi_unit").value == "nb⁻¹"
    assert app.number_input(key="test_lumi").value == pytest.approx(20.0)
    assert app.session_state["result_fb"] == pytest.approx(2e-5)
    app.selectbox(key="test_lumi_unit").set_value("pb⁻¹").run()
    assert app.number_input(key="test_lumi").value == pytest.approx(.02)
    assert app.session_state["result_fb"] == pytest.approx(2e-5)
    app.selectbox(key="test_lumi_unit").set_value("fb⁻¹").run()
    assert app.number_input(key="test_lumi").value == pytest.approx(2e-5)
    assert not app.exception
