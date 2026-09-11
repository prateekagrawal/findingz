import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from findingz.run_choices import fresh_config, matching_run, rename_saved_run
from findingz.simulation import ToySimulationConfig, run_toy_simulation


def test_duplicate_and_fresh_seed(tmp_path):
    config = ToySimulationConfig(events=100, label="Original")
    run = run_toy_simulation(config, tmp_path)
    changed = config.model_copy(update={"label": "New name"})
    assert matching_run(changed, tmp_path, "test").manifest_path == run.manifest_path
    fresh = fresh_config(changed, tmp_path, "test")
    assert fresh.seed != changed.seed
    assert fresh.model_dump(exclude={"seed"}) == changed.model_dump(exclude={"seed"})
    assert matching_run(fresh, tmp_path, "test") is None
    before = json.loads(run.manifest_path.read_text())
    rename_saved_run(run.manifest_path, "Renamed")
    after = json.loads(run.manifest_path.read_text())
    assert after == {**before, "label": "Renamed"}


@pytest.mark.parametrize("action", ["Load existing run", "Rename existing run", "Cancel"])
def test_duplicate_choice_does_not_generate(tmp_path, monkeypatch, action):
    config = ToySimulationConfig(events=100, label="Original")
    run = run_toy_simulation(config, tmp_path)
    original = run.analysis_path.read_bytes()
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path))
    def unexpected(*args, **kwargs):
        raise AssertionError("Should not generate events")
    monkeypatch.setattr("findingz.simulation.run_toy_simulation", unexpected)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"))
    app.session_state["duplicate_run"] = {
        "existing": matching_run(config, tmp_path, "test"),
        "config": config.model_copy(update={"label": "Requested"}),
        "toolchain": SimpleNamespace(image_id="test"), "depth": "Toy",
        "fresh": fresh_config(config, tmp_path, "test"),
    }
    app.run(timeout=30)
    assert not app.exception
    if action == "Cancel":
        app.button(key="duplicate_cancel").click().run()
    else:
        app.radio(key="duplicate_action").set_value(action).run()
        app.button(key="duplicate_continue").click().run()
    assert not app.exception
    expected = "Requested" if action == "Rename existing run" else "Original"
    assert json.loads(run.manifest_path.read_text())["label"] == expected
    assert run.analysis_path.read_bytes() == original
