from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("url", [None, "", "   ", "https://example.org/lab"])
def test_notebook_link_requires_explicit_configuration(tmp_path, monkeypatch, url):
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path))
    if url is None:
        monkeypatch.delenv("FINDINGZ_JUPYTER_URL", raising=False)
    else:
        monkeypatch.setenv("FINDINGZ_JUPYTER_URL", url)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    links = [
        item for item in app.get("link_button")
        if item.proto.label == "Open Jupyter analysis"
    ]
    if url and url.strip():
        assert len(links) == 1
        assert links[0].proto.url == url
    else:
        assert not links
        assert any(
            "Open the starter notebook, notebooks/06_sample_analysis.ipynb" in item.value
            for item in app.caption
        )
