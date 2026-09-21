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
    assert first.name == "my-analysis.ipynb"
    assert second.name == "my-analysis-2.ipynb"
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


@pytest.mark.parametrize("kernel", ["findingz", "hep"])
def test_export_requests_deployment_kernel(tmp_path, monkeypatch, kernel):
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_KERNEL", kernel)
    document = json.loads(save_notebook("kernel-test").read_text())
    assert document["metadata"]["kernelspec"]["name"] == kernel


def test_short_settings_and_editable_choices(tmp_path, monkeypatch):
    from findingz.notebook_analysis import load_analysis
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    monkeypatch.delenv("FINDINGZ_NOTEBOOK_TEMPLATE", raising=False)
    snapshot = {"plot": {"samples": ["signal", "background"], "observable": "mll",
        "windows": {"mll": [80, 100]}, "sample_configs": {"signal": "x" * 10000}},
        "count": None}
    path = save_notebook("short", snapshot)
    doc = json.loads(path.read_text())
    tagged = {tag: cell["source"] for cell in doc["cells"]
              for tag in cell.get("metadata", {}).get("tags", [])}
    assert len(tagged["findingz-settings"].splitlines()) == 4
    assert "sample_configs" not in path.read_text()
    namespace = {}
    exec(tagged["findingz-plot-choices"], namespace)
    exec(tagged["findingz-cut-choices"], namespace)
    assert namespace["sample_ids"] == ["signal", "background"]
    assert namespace["cuts"] == {"mll": [80, 100]}
    assert load_analysis(path.with_suffix(".settings.json")) == snapshot
    # Moving the pair together works without the original notebook directory.
    moved = tmp_path / "moved"
    moved.mkdir()
    sidecar = path.with_suffix(".settings.json")
    sidecar.rename(moved / sidecar.name)
    path.rename(moved / path.name)
    monkeypatch.chdir(moved)
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path / "unavailable"))
    assert load_analysis(sidecar.name) == snapshot
    with pytest.raises(FileNotFoundError, match="Keep the .settings.json"):
        load_analysis("missing.settings.json")


def test_existing_settings_are_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    orphan = tmp_path / "analysis.settings.json"
    orphan.write_text("original")
    path = save_notebook("analysis")
    assert path.name == "analysis-2.ipynb"
    assert orphan.read_text() == "original"


def test_export_does_not_reinterpret_legacy_count_roles(tmp_path, monkeypatch):
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="legacy additive"):
        save_notebook("legacy", {"count": {"signal": "s", "backgrounds": ["b"]}})
    assert not list(tmp_path.glob("*.ipynb"))


def test_ui_saves_without_server(tmp_path, monkeypatch):
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path / "runs"))
    monkeypatch.delenv("FINDINGZ_NOTEBOOK_URL_PREFIX", raising=False)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)
    next(b for b in app.button if b.label == "Save blank template notebook").click().run()
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


def test_save_then_link_without_duplicate_on_rerun(tmp_path, monkeypatch):
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_DIR", str(tmp_path))
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("FINDINGZ_NOTEBOOK_URL_PREFIX", "https://example.org/lab/tree/")
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)
    assert not app.get("link_button")
    next(b for b in app.button if b.label == "Save blank template notebook").click().run()
    assert not app.exception
    saved = Path(app.session_state["saved_analysis_notebook"])
    link = next(item for item in app.get("link_button")
                if item.proto.label == "Open saved notebook in JupyterLab")
    assert link.proto.url == notebook_url(saved)
    app.run()
    assert len(list(tmp_path.glob("*.ipynb"))) == 1
