import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from findingz.notebook_export import save_notebook, notebook_url, template_path


def test_unique_safe_names_and_blank_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    monkeypatch.delenv("FINDINGZ_NOTEBOOK_TEMPLATE", raising=False)
    first = save_notebook("../../my analysis")
    original = first.read_bytes()
    second = save_notebook("../../my analysis")
    assert first != second and first.parent == tmp_path
    assert first.read_bytes() == original
    doc = json.loads(original)
    namespace = {"display": lambda *_: None}
    for cell in doc["cells"]:
        if cell["cell_type"] == "code":
            exec(cell["source"], namespace)
    assert namespace["analysis"] == {"plot": None, "count": None}


def test_external_template_reload_and_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path / "saved"))
    template = json.loads(template_path().read_text())
    custom = tmp_path / "template.ipynb"
    custom.write_text(json.dumps(template))
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_TEMPLATE", str(custom))
    first = save_notebook("test", {"plot": {"samples": ["a"]}, "count": None})
    template["cells"][0]["source"] = "Changed course template"
    custom.write_text(json.dumps(template))
    second = save_notebook("test")
    assert json.loads(second.read_text())["cells"][0]["source"] == "Changed course template"
    assert json.loads(first.read_text())["cells"][0]["source"] != "Changed course template"
    custom.write_text("{}")
    with pytest.raises(ValueError, match="tagged"):
        save_notebook("bad")


@pytest.mark.parametrize("prefix", ["", "https://example.org/user/test/lab/tree/notebooks/"])
def test_ui_saves_without_server(tmp_path, monkeypatch, prefix):
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_URL_PREFIX", prefix)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)
    next(b for b in app.button if b.label == "Start from blank template").click().run()
    assert not app.exception
    saved = Path(app.session_state["saved_analysis_notebook"])
    assert saved.exists()
    assert bool(notebook_url(saved)) == bool(prefix)
    assert any(str(tmp_path) in item.value for item in app.caption)

