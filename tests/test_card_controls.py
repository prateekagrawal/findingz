from streamlit.testing.v1 import AppTest
from findingz.card_controls import inactive_reason, pdf_choices


def test_dependencies_and_typed_inputs():
    app = AppTest.from_string('''
import streamlit as st
from findingz.ui import _render_run_card_editor
from findingz.run_card import RunCardOptions
st.session_state['result'] = _render_run_card_editor(
    RunCardOptions(editable=['scale','fixed_ren_scale','pdlabel','lhaid']), 'typed',
    lambda: {'scale':'91.188','fixed_ren_scale':'False','pdlabel':'nn23lo1','lhaid':'230000'},
    lambda: {'pdlabel': {'nn23lo1':'NNPDF builtin','lhapdf':'LHAPDF'},
             'lhaid': {'230000':'NNPDF NLO (230000)', '247000':'NNPDF LO (247000)'}})
''', default_timeout=30).run()
    def button(name):
        return next(b for b in app.button if b.label == name)
    def choice(name):
        return next(b for b in app.selectbox if b.label == 'New value for ' + name)
    assert button('scale').disabled
    assert button('lhaid').disabled
    button('fixed_ren_scale').click().run()
    choice('fixed_ren_scale').set_value(True).run()
    assert not button('scale').disabled
    button('scale').click().run()
    app.number_input[0].set_value(100.0).run()
    button('pdlabel').click().run()
    choice('pdlabel').set_value('lhapdf').run()
    assert not button('lhaid').disabled
    button('lhaid').click().run()
    choice('lhaid').set_value('247000').run()
    assert app.session_state['result'] == {'scale':100.0,'fixed_ren_scale':True,'pdlabel':'lhapdf','lhaid':247000}
    choice('fixed_ren_scale').set_value(False).run()
    assert button('scale').disabled
    assert not app.number_input
    assert 'scale' not in app.session_state['result']
    choice('fixed_ren_scale').set_value(True).run()
    button('scale').click().run()
    assert app.number_input[0].value == 91.188
    choice('pdlabel').set_value('nn23lo1').run()
    assert button('lhaid').disabled
    assert not any(b.label == 'New value for lhaid' for b in app.selectbox)
    assert 'lhaid' not in app.session_state['result']


def test_fixed_factorization_dependencies():
    assert inactive_reason('dsqrt_q2fact1', {'fixed_fac_scale':False})
    assert inactive_reason('dsqrt_q2fact1', {'fixed_fac_scale':True}) is None
    assert inactive_reason('dsqrt_q2fact2', {'fixed_fac_scale2':True}) is None


def test_pdf_options_only_include_existing_files(tmp_path):
    executable = tmp_path/'bin/mg5_aMC'
    executable.parent.mkdir()
    executable.touch()
    data=tmp_path/'Template/LO/lib/Pdfdata'
    data.mkdir(parents=True)
    (data/'cteq6l1.tbl').touch()
    result=pdf_choices(executable)
    assert 'cteq6l1' in result['pdlabel']
    assert 'nn23lo1' not in result['pdlabel']


def test_uninstalled_default_cannot_be_submitted_with_lhapdf():
    app = AppTest.from_string('''
import streamlit as st
from findingz.ui import _render_run_card_editor
from findingz.run_card import RunCardOptions
st.session_state['result'] = _render_run_card_editor(
    RunCardOptions(editable=['pdlabel','lhaid']), 'missing',
    lambda: {'pdlabel':'nn23lo1','lhaid':'230000'},
    lambda: {'pdlabel': {'nn23lo1':'builtin','lhapdf':'LHAPDF'},
             'lhaid': {'247000':'Installed set'}})
''', default_timeout=30).run()
    next(b for b in app.button if b.label == 'pdlabel').click().run()
    app.selectbox[0].set_value('lhapdf').run()
    assert app.session_state['result'] is None
    next(b for b in app.button if b.label == 'lhaid').click().run()
    menu = next(b for b in app.selectbox if b.label == 'New value for lhaid')
    assert '230000' not in menu.options
    menu.set_value('247000').run()
    assert app.session_state['result'] == {'pdlabel':'lhapdf','lhaid':247000}
