from __future__ import annotations

import json

import pandas as pd
import pytest

from findingz.simulation import ToySimulationConfig, run_toy_simulation


def test_toy_simulation_is_checkpointed_and_reproducible(tmp_path) -> None:
    config = ToySimulationConfig(events=500, seed=17)
    first = run_toy_simulation(config, tmp_path)
    second = run_toy_simulation(config, tmp_path)

    assert not first.reused
    assert second.reused
    assert first.run_dir == second.run_dir
    pd.testing.assert_frame_equal(
        pd.read_csv(first.analysis_path), pd.read_csv(second.analysis_path)
    )


def test_toy_simulation_reconstructs_a_z_peak(tmp_path) -> None:
    config = ToySimulationConfig(
        events=2_000,
        seed=225,
        continuum_fraction=0.1,
        detector_pt_resolution=0.01,
    )
    run = run_toy_simulation(config, tmp_path)
    frame = pd.read_csv(run.analysis_path)
    peak_fraction = frame["mll"].between(85.0, 97.0).mean()
    manifest = json.loads(run.manifest_path.read_text())

    assert peak_fraction > 0.65
    assert manifest["generated_events"] == 2_000
    assert manifest["accepted_events"] == len(frame)
    assert "not MadGraph" in manifest["provenance"]


def test_toy_simulation_rejects_unsafe_event_count() -> None:
    with pytest.raises(ValueError, match="less than or equal to 10000"):
        ToySimulationConfig(events=100_000)


def test_run_label_is_persistent_metadata_not_part_of_physics_hash(tmp_path) -> None:
    first = run_toy_simulation(ToySimulationConfig(events=100, label="First label"), tmp_path)
    second = run_toy_simulation(ToySimulationConfig(events=100, label="Renamed run"), tmp_path)
    manifest = json.loads(second.manifest_path.read_text())

    assert first.run_dir == second.run_dir
    assert second.reused
    assert manifest["label"] == "Renamed run"
    assert "label" not in manifest["config"]
