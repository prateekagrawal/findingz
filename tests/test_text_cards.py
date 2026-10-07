import pytest
from streamlit.testing.v1 import AppTest

from findingz.hep_pipeline import HepSimulationConfig, _pipeline_hash
from findingz.text_cards import validate_shower_card


def test_text_cards_are_part_of_identity_and_require_full_pipeline():
    config = HepSimulationConfig(detector_card_text="# custom detector")
    second = HepSimulationConfig(detector_card_text="# other detector")
    assert _pipeline_hash(config, "test") != _pipeline_hash(second, "test")
    for kwargs in ({"run_mode": "madgraph", "detector_card_text": "test"},
                   {"shower_card_text": ""}, {"detector_card_text": "a\0b"}):
        with pytest.raises(ValueError):
            HepSimulationConfig(**kwargs)
    with pytest.raises(ValueError, match="event-count"):
        validate_shower_card("Main:numberOfEvents = 10")
    with pytest.raises(ValueError, match="collect"):
        validate_shower_card("HEPMCoutput:file = /dev/null")


def test_editor_unchanged_text_preserves_defaults_and_clears_override():
    app = AppTest.from_string('''
import streamlit as st
from findingz.ui import _render_text_card_editor
from findingz.text_cards import TextCardOptions
st.session_state["result"] = _render_text_card_editor(
    TextCardOptions(editable=True), "Detector", "test", None, lambda: "# default card")
''', default_timeout=30).run()
    assert app.session_state["result"] == (None, True)
    assert not app.text_area
    next(box for box in app.checkbox if box.label == "Edit Detector").check().run()
    assert app.session_state["result"] == (None, True)
    app.text_area[0].set_value("# custom card").run()
    assert app.session_state["result"] == ("# custom card", True)
    app.text_area[0].set_value("").run()
    assert app.session_state["result"] == (None, False)
    next(box for box in app.checkbox if box.label == "Edit Detector").uncheck().run()
    assert app.session_state["result"] == (None, True)


def test_course_card_path_is_relative_and_loaded_without_student_edits(tmp_path):
    (tmp_path / "card.tcl").write_text("# course card")
    app = AppTest.from_string(f'''
import streamlit as st
from pathlib import Path
from findingz.ui import _render_text_card_editor
from findingz.text_cards import TextCardOptions
st.session_state["result"] = _render_text_card_editor(
    TextCardOptions(path="card.tcl"), "Detector", "test", Path({str(tmp_path / "catalog.yaml")!r}),
    lambda: "# default")
''', default_timeout=30).run()
    assert not app.exception
    assert app.session_state["result"] == ("# course card", True)


def test_full_ui_loads_schema_two_and_all_card_controls(tmp_path, monkeypatch):
    from pathlib import Path
    import yaml
    from findingz.catalog import load_catalog
    payload = load_catalog().model_dump(mode="json")
    payload.update(schema_version=2, datasets={}, run_card={"editable": ["ptl"]},
                   param_card={"editable": ["mass 23"]},
                   shower_card={"editable": True}, detector_card={"editable": True})
    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    monkeypatch.setenv("FINDINGZ_CATALOG_PATH", str(path))
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path / "runs"))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "findingz/ui.py"), default_timeout=30).run()
    assert not app.exception
    run_type = next(box for box in app.selectbox if box.label == "Run type")
    run_type.set_value("Full pipeline (MadGraph + Pythia8 + Delphes/FastJet)").run()
    assert not app.exception
    assert {box.label for box in app.button} >= {"ptl", "mass 23"}
    assert {box.label for box in app.checkbox} >= {"Edit Pythia shower card", "Edit Delphes detector card"}


def test_restore_and_uncheck_discard_text_edits():
    app = AppTest.from_string('''
import streamlit as st
from findingz.ui import _render_text_card_editor
from findingz.text_cards import TextCardOptions
st.session_state['result'] = _render_text_card_editor(
    TextCardOptions(editable=True), 'Detector', 'test', None, lambda: '# default card')
''', default_timeout=30).run()
    next(box for box in app.checkbox if box.label == "Edit Detector").check().run()
    app.text_area[0].set_value('# changed').run()
    assert app.session_state['result'] == ('# changed', True)
    next(b for b in app.button if b.label == 'Restore defaults').click().run()
    assert app.text_area[0].value == '# default card'
    assert app.session_state['result'] == (None, True)
    app.text_area[0].set_value('# another edit').run()
    next(box for box in app.checkbox if box.label == "Edit Detector").uncheck().run()
    assert app.session_state['result'] == (None, True)
    next(box for box in app.checkbox if box.label == "Edit Detector").check().run()
    assert app.text_area[0].value == '# default card'
