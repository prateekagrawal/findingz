from __future__ import annotations

import gzip

import pytest

from findingz.hep_pipeline import (
    MAX_HEP_EVENTS,
    HepSimulationConfig,
    HepToolchainReport,
    _apply_standard_retention,
    _pipeline_hash,
    extract_cross_section,
    extract_lhe_truth,
    probe_hep_toolchain,
    render_delphes_card,
    render_madevent_commands,
    render_madgraph_process_card,
    resolve_detector_card,
    run_hep_simulation,
)


def test_madgraph_card_contains_full_neutral_current_process(tmp_path) -> None:
    config = HepSimulationConfig(process="dy_ll")
    card = render_madgraph_process_card(config, tmp_path / "process")
    assert "generate p p > e+ e- QED=2 QCD=0" in card
    assert "add process p p > mu+ mu- QED=2 QCD=0" in card
    assert f"output {tmp_path / 'process'} -f" in card


def test_madevent_card_is_bounded_and_reproducible() -> None:
    config = HepSimulationConfig(events=500, seed=37, beam_energy_gev=6_800)
    card = render_madevent_commands(config, "run_01")
    assert "shower=Pythia8" in card
    assert "detector=Delphes" in card
    assert "set nevents 500" in card
    assert "set iseed 37" in card
    assert "set ebeam1 6800" in card
    assert "set mmllmax 130" in card


def test_standard_delphes_card_omits_heavy_low_level_collections() -> None:
    branches = [
        "Particle",
        "Track",
        "Tower",
        "EFlowTrack",
        "EFlowPhoton",
        "EFlowNeutralHadron",
        "Jet",
        "Electron",
    ]
    base = "\n".join(f"  add Branch Source/{name.lower()} {name} Class" for name in branches)

    standard = render_delphes_card(base, "standard")
    advanced = render_delphes_card(base, "advanced")

    assert "add Branch Source/jet Jet Class" in standard
    assert "add Branch Source/electron Electron Class" in standard
    assert "# FindingZ standard omits: add Branch Source/track Track Class" in standard
    assert "add Branch Source/track Track Class" in advanced


def test_ee_madgraph_card_sets_lepton_beams_and_model(tmp_path) -> None:
    config = HepSimulationConfig(
        collider="ee",
        model="loop_sm",
        process="ee_mumu",
        run_mode="madgraph",
        beam_energy_gev=45.6,
    )
    process_card = render_madgraph_process_card(config, tmp_path / "process")
    command_card = render_madevent_commands(config, "run_01")
    assert "import model loop_sm" in process_card
    assert "generate e+ e- > mu+ mu-" in process_card
    assert "shower=OFF" in command_card
    assert "detector=OFF" in command_card
    assert "set lpp1 0" in command_card
    assert "set ebeam1 45.6" in command_card


def test_ee_full_pipeline_uses_lepton_beams_and_selected_detector(tmp_path) -> None:
    delphes = tmp_path / "Delphes"
    card = delphes / "cards" / "delphes_card_ALEPH.tcl"
    card.parent.mkdir(parents=True)
    card.write_text("set ExecutionPath {}\n")
    config = HepSimulationConfig(
        collider="ee",
        process="ee_mumu",
        process_lines=["generate e+ e- > mu+ mu- QED=2 QCD=0"],
        run_mode="full",
        beam_energy_gev=45.6,
        detector_id="aleph",
        detector_card="cards/delphes_card_ALEPH.tcl",
    )
    toolchain = HepToolchainReport(
        available=True,
        mg5_executable=tmp_path / "mg5_aMC",
        pythia8_dir=tmp_path / "pythia8",
        delphes_dir=delphes,
        delphes_card=None,
        image_id="test",
        detail="test",
    )

    command_card = render_madevent_commands(config, "run_01")
    assert "set lpp1 0" in command_card
    assert "shower=Pythia8" in command_card
    assert "detector=Delphes" in command_card
    assert resolve_detector_card(config, toolchain) == card


def test_detector_card_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="safe path"):
        HepSimulationConfig(detector_card="../outside.tcl")


def test_extracts_final_madgraph_cross_section(tmp_path) -> None:
    log = tmp_path / "event_generation.log"
    log.write_text("Cross-section : 1338.2 +- 8.20 pb\nCross-section :   1332 +- 7.418 pb\n")
    assert extract_cross_section(log) == (1332.0, 7.418)


def test_hep_config_rejects_large_run() -> None:
    with pytest.raises(ValueError, match="less than or equal to 10000"):
        HepSimulationConfig(events=MAX_HEP_EVENTS + 1)


def test_hep_run_label_does_not_change_physics_hash() -> None:
    first = HepSimulationConfig(label="First label")
    renamed = HepSimulationConfig(label="Renamed run")
    assert _pipeline_hash(first, "image") == _pipeline_hash(renamed, "image")


def test_checkpoint_reuse_reports_progress(tmp_path) -> None:
    config = HepSimulationConfig(run_mode="madgraph")
    image_id = "test-image"
    run_dir = tmp_path / f"finding-z-hep-{_pipeline_hash(config, image_id)}"
    run_dir.mkdir()
    (run_dir / "truth.csv").write_text("event_id,mll\n1,91\n")
    (run_dir / "analysis.csv").write_text("event_id,mll\n1,91\n")
    (run_dir / "manifest.json").write_text(
        '{"status":"complete","stages":{"analysis":"analysis.csv"}}'
    )
    toolchain = HepToolchainReport(
        available=True,
        mg5_executable=tmp_path / "mg5_aMC",
        pythia8_dir=tmp_path / "pythia8",
        delphes_dir=tmp_path / "Delphes",
        delphes_card=tmp_path / "delphes_card.dat",
        image_id=image_id,
        detail="test",
    )
    updates: list[tuple[str, float]] = []

    result = run_hep_simulation(config, tmp_path, toolchain=toolchain, progress=lambda *x: updates.append(x))

    assert result.reused
    assert updates[0][0] == "Checking the generator toolchain"
    assert updates[-1] == ("Checkpoint ready", 1.0)


def test_standard_retention_removes_transient_outputs_only_after_validation(tmp_path) -> None:
    retained = {
        "matrix_element": "matrix_element/events.lhe.gz",
        "detector_root": "detector/delphes.root",
        "detector_csv": "detector/detector.csv",
        "analysis": "analysis.csv",
        "shower": "shower/events.hepmc.gz",
    }
    for relative_path in retained.values():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("checkpoint")
    process_output = tmp_path / "process" / "Events" / "run_01" / "events.hepmc.gz"
    process_output.parent.mkdir(parents=True)
    process_output.write_text("large transient")
    (process_output.parent / "tag_1_pythia8.log").write_text("shower diagnostics")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/event_generation.log").write_text(
        "INFO: can not run systematics since can not link python to lhapdf\n"
    )
    manifest: dict[str, object] = {"stages": retained}

    _apply_standard_retention(tmp_path, manifest)

    assert not (tmp_path / "process").exists()
    assert not (tmp_path / "shower").exists()
    assert (tmp_path / "detector" / "delphes.root").exists()
    assert (tmp_path / "matrix_element" / "events.lhe.gz").exists()
    assert "shower" not in manifest["stages"]
    assert manifest["retention"]["profile"] == "standard-v1"
    diagnostic = "logs/process/Events/run_01/tag_1_pythia8.log"
    assert (tmp_path / diagnostic).read_text() == "shower diagnostics"
    assert diagnostic in manifest["diagnostic_logs"]
    assert manifest["systematics"]["status"] == "skipped"


def test_standard_retention_preserves_transients_when_checkpoint_is_missing(tmp_path) -> None:
    process_output = tmp_path / "process" / "Events" / "run_01" / "events.hepmc.gz"
    process_output.parent.mkdir(parents=True)
    process_output.write_text("diagnostic output")
    manifest: dict[str, object] = {"stages": {"analysis": "missing.csv"}}

    with pytest.raises(RuntimeError, match="missing or empty"):
        _apply_standard_retention(tmp_path, manifest)

    assert process_output.exists()


def test_lhe_truth_extraction(tmp_path) -> None:
    lhe = """<LesHouchesEvents version=\"3.0\">
<event>
4 1 1.0 91.0 0.007 0.118
11 1 1 2 0 0 30.0 0.0 35.0 46.0977 0.000511 0.0 1.0
-11 1 1 2 0 0 -30.0 0.0 -35.0 46.0977 0.000511 0.0 -1.0
1 -1 0 0 501 0 0.0 0.0 6500.0 6500.0 0.0 0.0 -1.0
-1 -1 0 0 0 501 0.0 0.0 -6500.0 6500.0 0.0 0.0 -1.0
</event>
</LesHouchesEvents>
"""
    path = tmp_path / "events.lhe.gz"
    with gzip.open(path, "wt") as destination:
        destination.write(lhe)
    frame = extract_lhe_truth(path)
    assert len(frame) == 1
    assert frame.iloc[0]["channel"] == "ee"
    assert frame.iloc[0]["l1_charge"] == -1
    assert frame.iloc[0]["l2_charge"] == 1


def test_local_host_reports_missing_hep_stack() -> None:
    report = probe_hep_toolchain()
    assert isinstance(report.available, bool)
    assert report.detail
