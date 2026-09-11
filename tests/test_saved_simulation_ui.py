from pathlib import Path

from streamlit.testing.v1 import AppTest

from findingz.simulation import ToySimulationConfig, run_toy_simulation


def test_open_saved_results_after_reload(tmp_path, monkeypatch):
    run = run_toy_simulation(ToySimulationConfig(label="Recall me"), tmp_path)
    other = run_toy_simulation(ToySimulationConfig(label="Another run", seed=226), tmp_path)
    original = run.manifest_path.read_bytes()
    monkeypatch.setenv("FINDINGZ_RUN_ROOT", str(tmp_path))
    app_path = str(Path(__file__).parents[1] / "app.py")
    for _ in range(2):
        app = AppTest.from_file(app_path).run(timeout=30)
        assert not app.exception
        app.radio(key="simulation_view").set_value("Saved runs").run()
        app.selectbox(key="simulation_saved_run").set_value(run.run_dir.name).run()
        assert not any(button.label == "Open results" for button in app.button)
        assert not app.exception
        assert any("Opened saved run" in item.value for item in app.success)
        assert app.session_state["simulation_run"]["recalled"]
        assert run.manifest_path.read_bytes() == original
        assert not any(button.label == "Run MadGraph" for button in app.button)
        app.selectbox(key="simulation_saved_run").set_value(other.run_dir.name).run()
        assert not app.exception
        assert any("Another run" in item.value for item in app.success)
        app.selectbox(key="simulation_saved_run").set_value(None).run()
        assert not app.exception
        assert not any("Opened saved run" in item.value for item in app.success)
