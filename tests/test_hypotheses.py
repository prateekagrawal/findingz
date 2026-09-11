from __future__ import annotations

import json

import pandas as pd
import pytest

from findingz.catalog import DatasetEntry, load_catalog
from findingz.hypotheses import (
    AnalysisSample,
    build_sample_library,
    compatible_counting_backgrounds,
    select_events,
    validate_analysis_context,
    validate_counting_samples,
)


def test_course_and_student_samples_use_identical_run_normalization(tmp_path):
    root = tmp_path / "student"
    root.mkdir()
    course_root = tmp_path / "course"
    course_root.mkdir()
    for parent, name in [(root, "student-run"), (course_root, "course-run")]:
        run_dir = parent / name
        run_dir.mkdir()
        (run_dir / "analysis.csv").write_text("mll,weight\n91,1\n92,1\n")
        (run_dir / "manifest.json").write_text(json.dumps({
            "run_id": name, "status": "complete", "pipeline": "MadGraph",
            "config": {"run_mode": "madgraph", "collider_id": "lhc13",
                       "beam_energy_gev": 6500.0},
            "generated_events": 2, "cross_section_pb": 2.0,
            "stages": {"analysis": "analysis.csv"},
        }))
    catalog = load_catalog()
    catalog.datasets["reference"] = DatasetEntry(
        label="Reference sample", path=str(course_root / "course-run"), provenance="Course run"
    )
    # Even an older catalogue that enables the CSV templates must not resurrect them.
    catalog.datasets["signal"].enabled = True
    library = build_sample_library(catalog, root)
    assert set(library) == {"run:course-run", "run:student-run"}
    first, second = library.values()
    assert first.kind == second.kind == "generated"
    assert first.menu_label == "Reference sample"
    assert "[generated" not in second.menu_label
    validate_counting_samples([first, second])
    assert first.expected_frame(1.0).weight.sum() == second.expected_frame(1.0).weight.sum() == 2000
    catalog.datasets["reference"].enabled = False
    assert set(build_sample_library(catalog, root)) == {"run:student-run"}


def _sample(
    tmp_path,
    name: str,
    *,
    kind="generated",
    energy=6500.0,
    mass_window=(50.0, 130.0),
):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame(
        {
            "channel": ["mumu", "mumu"],
            "weight": [1.0, 1.0],
            "mll": [91.0, 120.0],
            "l1_pt": [45.0, 10.0],
            "l2_pt": [44.0, 10.0],
            "l1_eta": [0.2, 0.1],
            "l2_eta": [-0.2, -0.1],
        }
    ).to_csv(path, index=False)
    return AnalysisSample(
        sample_id=name,
        label=name,
        kind=kind,
        path=path,
        provenance="test",
        config={
            "collider_id": "lhc13",
            "beam_energy_gev": energy,
            "run_mode": "madgraph",
            "detector_id": "none",
            "output_detail": "standard",
            "min_mass_gev": mass_window[0],
            "max_mass_gev": mass_window[1],
        },
        generated_events=100,
        cross_section_pb=2.0,
    )


def test_generated_expected_yield_uses_cross_section_and_luminosity(tmp_path) -> None:
    sample = _sample(tmp_path, "signal")
    frame = sample.expected_frame(10.0)
    assert frame["weight"].sum() == pytest.approx(400.0)


def test_selection_applies_object_and_mass_cuts(tmp_path) -> None:
    frame = _sample(tmp_path, "signal").load()
    selected = select_events(
        frame,
        channels=["mumu"],
        minimum_pt=20.0,
        maximum_abs_eta=2.5,
        mass_window=(80.0, 100.0),
    )
    assert selected["mll"].tolist() == [91.0]


def test_counting_requires_consistent_generated_context(tmp_path) -> None:
    signal = _sample(tmp_path, "signal")
    incompatible = _sample(tmp_path, "background", energy=120.0)
    with pytest.raises(ValueError, match="same collider"):
        validate_counting_samples([signal, incompatible])


def test_background_menu_uses_execution_compatibility_checks(tmp_path):
    signal = _sample(tmp_path, "signal")
    good = _sample(tmp_path, "background")
    good.config.update(model="different-theory", process="different-process")
    wrong_energy = _sample(tmp_path, "wrong-energy", energy=100.)
    wrong_window = _sample(tmp_path, "wrong-window", mass_window=(10., 200.))
    full = _sample(tmp_path, "full")
    full.config.update(run_mode="full", detector_id="cms")
    legacy = _sample(tmp_path, "legacy", kind="prepared")
    library = {s.sample_id: s for s in [signal, good, wrong_energy, wrong_window, full, legacy]}
    assert compatible_counting_backgrounds(signal, library) == [good.sample_id]


def test_counting_explains_actual_simulation_and_detector_mismatch(tmp_path):
    full = _sample(tmp_path, "full-run")
    full.config.update(run_mode="full", detector_id="cms")
    parton = _sample(tmp_path, "parton-run")
    with pytest.raises(ValueError) as raised:
        validate_counting_samples([full, parton])
    message = str(raised.value)
    assert "simulation level (full-run: MadGraph + Pythia + Delphes" in message
    assert "parton-run: MadGraph only (parton level)" in message
    assert "detector (full-run: cms; parton-run: no detector)" in message


def test_counting_requires_consistent_generated_phase_space(tmp_path) -> None:
    signal = _sample(tmp_path, "signal")
    incompatible = _sample(tmp_path, "background", mass_window=(80.0, 100.0))
    with pytest.raises(ValueError, match="generated mass range"):
        validate_counting_samples([signal, incompatible])


def test_analysis_context_describes_generated_configuration(tmp_path) -> None:
    sample = _sample(tmp_path, "signal")
    assert sample.analysis_context == sample.generated_context
    assert "√s = 13000 GeV" in sample.analysis_context_label


def test_prepared_samples_live_in_explicit_legacy_context(tmp_path) -> None:
    prepared = _sample(tmp_path, "prepared", kind="prepared")
    assert prepared.analysis_context == ("legacy-synthetic-z",)
    assert "not collider simulation" in prepared.analysis_context_label


def test_plots_reject_different_collider_configurations(tmp_path) -> None:
    first = _sample(tmp_path, "first")
    second = _sample(tmp_path, "second", energy=120.0)
    with pytest.raises(ValueError, match="All plotted hypotheses"):
        validate_analysis_context([first, second])


def test_counting_rejects_mixed_prepared_and_generated_samples(tmp_path) -> None:
    generated = _sample(tmp_path, "generated")
    prepared = _sample(tmp_path, "prepared", kind="prepared")
    with pytest.raises(ValueError, match="cannot mix"):
        validate_counting_samples([generated, prepared])
