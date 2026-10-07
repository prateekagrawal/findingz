from streamlit.testing.v1 import AppTest


def test_editor_defaults_valid_edits_and_invalid_input():
    app = AppTest.from_string('''
import streamlit as st
from findingz.ui import _render_run_card_editor
from findingz.run_card import RunCardOptions
settings = _render_run_card_editor(
    RunCardOptions(defaults={"ptl": 10.0}, editable=["ptl", "cut_decays"]), "test",
    lambda: {"ptl": "20", "cut_decays": "True"})
st.session_state["settings"] = settings
st.button("Run", disabled=settings is None)
''', default_timeout=30).run()
    assert not app.exception
    assert app.session_state['settings'] == {'ptl': 10.0}
    next(b for b in app.button if b.label == "ptl").click().run()
    next(b for b in app.button if b.label == "cut_decays").click().run()
    assert app.number_input[0].value == 10.0
    assert app.selectbox[0].value is True
    assert app.session_state['settings'] == {'ptl': 10.0}  # no unnecessary overrides
    app.number_input[0].set_value(25.0).run()
    app.selectbox[0].set_value(False).run()
    assert app.session_state['settings'] == {'ptl': 25, 'cut_decays': False}
    next(b for b in app.button if b.label == "ptl").click().run()
    assert app.session_state['settings'] == {'ptl': 10.0, 'cut_decays': False}
    app.button[0].click().run()
    assert not app.number_input
    assert app.session_state['settings'] == {'ptl': 10.0}


def test_parameter_editor_and_missing_default():
    app = AppTest.from_string('''
import streamlit as st
from findingz.ui import _render_param_card_editor
from findingz.param_card import ParamCardOptions
st.session_state['settings'] = _render_param_card_editor(
    ParamCardOptions(editable=['mass 23', 'decay 23', 'mass 999']), 'test',
    lambda: {'mass 23': '9.1188e1', 'decay 23': '2.4952'})
''', default_timeout=30).run()
    next(b for b in app.button if b.label == "mass 23").click().run()
    assert app.session_state['settings'] == {}
    app.number_input[0].set_value(92.0).run()
    assert app.session_state['settings'] == {'mass 23': 92.}
    app.number_input[0].set_value(91.188).run()
    assert app.session_state['settings'] == {}
    assert next(b for b in app.button if b.label == "mass 999").disabled
    assert not app.error


def test_old_catalog_has_no_editor():
    app = AppTest.from_string('''
from findingz.ui import _render_run_card_editor
from findingz.run_card import RunCardOptions
assert _render_run_card_editor(RunCardOptions(), "old") == {}
''', default_timeout=30).run()
    assert not app.exception
    assert not app.get("button_group")


def test_parameter_rows_follow_course_order_not_click_order():
    app = AppTest.from_string('''
import streamlit as st
from findingz.ui import _render_run_card_editor
from findingz.run_card import RunCardOptions
_render_run_card_editor(RunCardOptions(editable=['ptl', 'etal', 'mmll']), 'ordered',
                        lambda: {'ptl':'10.0','etal':'2.5','mmll':'0.0'})
''', default_timeout=30).run()
    for name in ['mmll', 'ptl', 'etal']:
        next(b for b in app.button if b.label == name).click().run()
    assert [field.label for field in app.number_input] == [
        'New value for ptl', 'New value for etal', 'New value for mmll']
