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


def test_ui_saves_without_server(tmp_path, monkeypatch):
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path / "runs"))
    monkeypatch.delenv("FINDINGZ_NOTEBOOK_URL_PREFIX", raising=False)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)
    next(b for b in app.button if b.label == "Start from blank template").click().run()
    assert not app.exception
    saved = Path(app.session_state["saved_analysis_notebook"])
    assert saved.exists()
    assert notebook_url(saved) is None
    assert any(str(tmp_path) in item.value for item in app.caption)


def test_notebook_link_uses_configured_prefix(monkeypatch):
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_URL_PREFIX", "https://example.org/user/a/lab/tree/notebooks/")
    assert notebook_url(Path("/storage/a notebook.ipynb")) == (
        "https://example.org/user/a/lab/tree/notebooks/a%20notebook.ipynb"
    )


def test_launch_request_is_saved_once(tmp_path, monkeypatch):
    import streamlit as st
    from types import SimpleNamespace
    from findingz import notebook_launch

    def fake_component(**kwargs):
        clicked = st.button("Test browser click")
        # Emulate a trigger retained across the immediate rerun.
        if clicked:
            st.session_state["test_launch_requested"] = True
        return SimpleNamespace(request={"id": "test-click", "mode": "blank"}
                               if st.session_state.get("test_launch_requested") else None)

    monkeypatch.setattr(notebook_launch, "launch_buttons", fake_component)
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_URL_PREFIX", "https://example.org/lab/tree/")
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)
    next(b for b in app.button if b.label == "Test browser click").click().run()
    assert not app.exception
    assert len(list(tmp_path.glob("*.ipynb"))) == 1
    assert app.session_state["notebook_launch_reply"]["url"].startswith("https://example.org/")
