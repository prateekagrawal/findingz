import gzip
import math

import pytest

from findingz.event_display import event_figure, lhe_events, read_event, read_lhe_event


@pytest.mark.parametrize("compressed", [False, True])
def test_lhe_final_state_and_event_selection(tmp_path, compressed):
    event = """<event>
4 1 1 1 1 1
11 -1 0 0 0 0 0 0 100 100 0 0 1
23 2 0 0 0 0 0 0 0 200 200 0 1
13 1 0 0 0 0 3.0D+1 0 40 50 0 0 1
-13 1 0 0 0 0 -30 0 -40 50 0 0 1
<rwgt><wgt id="a">2</wgt></rwgt>
</event>"""
    path = tmp_path / ("events.lhe.gz" if compressed else "events.lhe")
    text = ("<LesHouchesEvents>\n<header>unescaped x < 2 & y > 3</header>\n"
            + event + event.replace("13 1", "1 1") + "</LesHouchesEvents>")
    if compressed:
        with gzip.open(path, "wt") as output:
            output.write(text)
    else:
        path.write_text(text)
    assert len(list(lhe_events(path))) == 2
    first = read_lhe_event(path, 0)
    assert first["PDG ID"].tolist() == [13, -13]
    assert first.iloc[0]["pT [GeV]"] == 30
    assert set(read_lhe_event(path, 1)["Object"]) == {"Quark"}
    assert "parton level" in event_figure(first, parton_level=True).axes[0].get_title()
    with pytest.raises(IndexError):
        read_lhe_event(path, 2)


class Tree:
    num_entries = 2

    def keys(self):
        return ["Muon.PT", "Muon.Eta", "Muon.Phi", "Muon.Charge",
                "MissingET.MET", "MissingET.Phi"]

    def arrays(self, fields, *, entry_start, entry_stop, library):
        assert entry_stop == entry_start + 1
        values = [[40], [0.2], [-1], [-1], [20], [2]]
        return {key: [value if entry_start == 0 else []]
                for key, value in zip(self.keys(), values, strict=True) if key in fields}


def test_selected_event_and_missing_collections():
    objects, met, missing = read_event(Tree(), 0)
    assert objects.iloc[0]["pT [GeV]"] == 40
    assert objects.iloc[0]["Charge"] == -1
    assert met == [(20, 2)]
    assert missing == ["Electron", "Photon", "Jet"]
    figure = event_figure(objects)
    assert len(figure.axes[0].collections) == 1
    assert figure.axes[0].get_ylim() == (-math.pi, math.pi)


def test_empty_event_and_bounds():
    objects, met, _ = read_event(Tree(), 1)
    assert objects.empty and not met
    assert not event_figure(objects).axes[0].collections
    with pytest.raises(IndexError):
        read_event(Tree(), 2)


def test_nested_delphes_branch_names():
    class NestedTree(Tree):
        def keys(self):
            names = super().keys()
            return [name.split(".")[0] + "/" + name for name in names]

        def arrays(self, fields, **kwargs):
            return Tree().arrays(fields, **kwargs)

    objects, met, missing = read_event(NestedTree(), 0)
    assert len(objects) == 1 and met == [(20, 2)]
    assert "Muon" not in missing


def test_event_buttons_without_checkbox():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string(
        "import streamlit as st\nfrom findingz.event_display import event_controls\n"
        "selected = event_controls(10, 'test_event')\n"
        "if selected is not None: st.write(f'Displaying {selected}')"
    ).run()
    assert not app.checkbox and not app.exception
    app.number_input[0].set_value(4).run()
    next(b for b in app.button if b.label == "Show event").click().run()
    assert any("Displaying 4" in item.value for item in app.markdown)
    next(b for b in app.button if b.label == "Random event").click().run()
    assert not app.exception
    assert 1 <= app.session_state["shown_test_event"] <= 10
