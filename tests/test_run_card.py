import hashlib
import json
from pathlib import Path

import pytest

from findingz.catalog import CourseCatalog, load_catalog
from findingz.hep_pipeline import HepSimulationConfig, HepToolchainReport, _pipeline_hash, run_hep_simulation, extract_lhe_truth
from findingz.run_card import RunCardOptions, apply_overrides, parse_edits


def test_course_policy_and_native_syntax():
    policy = RunCardOptions(defaults={"ptl": 10., "cut_decays": True}, editable=["ptl", "etal"])
    edits = parse_edits("2.5d1 = ptl ! GeV\n2.4 = etal\n", policy)
    assert edits == {"ptl": 25., "etal": 2.4, "cut_decays": True}
    assert parse_edits("", policy) == policy.defaults
    source = "# default = ptl\n 10 = ptl ! GeV\n 5 = etal\n False = cut_decays\n 1000 = nevents\n"
    result = apply_overrides(source, edits)
    assert "25.0 = ptl ! GeV" in result
    assert "True = cut_decays" in result
    assert "1000 = nevents" in result
    assert "# default = ptl" in result


@pytest.mark.parametrize("text", ["2 = mass", "2 = ptl\n3 = ptl", "set ptl 2", "nan = ptl",
                                   "1e999 = ptl", "2; quit = ptl", "[1,2] = ptl"])
def test_reject_invalid_student_edits(text):
    with pytest.raises(ValueError):
        parse_edits(text, RunCardOptions(editable=["ptl"]))


@pytest.mark.parametrize("name", ["nevents", "iseed", "ebeam1", "lpp1", "ptl\nquit"])
def test_managed_fields_and_command_characters_rejected(name):
    with pytest.raises(ValueError):
        RunCardOptions(editable=[name])
    with pytest.raises(ValueError):
        HepSimulationConfig(run_card_overrides={name: 1})


def test_unknown_native_field_fails_instead_of_silently_ignoring():
    with pytest.raises(ValueError, match="absent.*typo"):
        apply_overrides(" 10 = ptl\n", {"typo": 1})
    with pytest.raises(ValueError, match="Duplicate"):
        apply_overrides("10 = ptl\n20 = ptl\n", {"ptl": 1})
    with pytest.raises(ValueError, match="legacy"):
        HepSimulationConfig(min_mass_gev=10, run_card_overrides={"mmll": 20})


def test_old_catalog_and_empty_cards_remain_compatible():
    payload = load_catalog().model_dump(mode="json")
    payload.pop("run_card")
    catalog = CourseCatalog.model_validate(payload)
    assert catalog.run_card == RunCardOptions()
    payload["run_card"] = {"editable": ["ptl"]}
    payload["processes"]["dy_ll"]["run_card"] = {"defaults": {"ptl": 5}}
    with pytest.raises(ValueError, match="schema_version: 2"):
        CourseCatalog.model_validate(payload)
    payload["schema_version"] = 2
    catalog = CourseCatalog.model_validate(payload)
    assert catalog.processes["dy_ll"].run_card.editable == []
    config = HepSimulationConfig(run_mode="madgraph")
    old = config.model_dump(mode="json", exclude={"label", "beam2_energy_gev", "model_ufo_path", "run_card_overrides", "param_card_overrides", "shower_card_text", "detector_card_text"})
    digest = hashlib.sha256(json.dumps({"schema_version": 2, "analysis_schema": 2, "config": old, "image_id": "test"},
                                     sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:10]
    assert _pipeline_hash(config, "test") == digest
    changed = HepSimulationConfig(run_mode="madgraph", run_card_overrides={"ptl": 5})
    assert _pipeline_hash(changed, "test") != digest


@pytest.mark.parametrize("full", [False, True])
def test_pipeline_edits_before_generation_and_retains_card_and_manifest(tmp_path, monkeypatch, full):
    generated_lhe = None
    class Runner:
        def run(self, argv, *, cwd, log_path, timeout_s):
            nonlocal generated_lhe
            log_path.write_text("test\n")
            if Path(argv[0]).name == "mg5_aMC":
                cards = cwd / "process" / "Cards"
                cards.mkdir(parents=True)
                (cards / "run_card.dat").write_text("10 = ptl ! cut\nTrue = cut_decays\n")
                (cards / "param_card.dat").write_text("BLOCK MASS\n23 91.2\n25 125.\n")
            else:
                assert "25.0 = ptl" in (cwd / "Cards/run_card.dat").read_text()
                assert "23  92.0" in (cwd / "Cards/param_card.dat").read_text()
                if full:
                    assert (cwd / "Cards/pythia8_card.dat").read_text() == shower
                    assert (cwd / "Cards/delphes_card.dat").read_text() == detector
                events = cwd / "Events/run_01"
                events.mkdir(parents=True)
                (events / "events.lhe").write_text(
                    "<LesHouchesEvents>\n<event>\n2 1 1 1 1 1\n"
                    "13 1 0 0 0 0 30 0 40 50 0 0 1\n"
                    "-13 1 0 0 0 0 -30 0 -40 50 0 0 1\n"
                    "</event>\n</LesHouchesEvents>\n")
                generated_lhe = events / "events.lhe"
                if full:
                    (events / "tag_1_delphes_events.root").write_text("test root\n")
                    (events / "tag_1_pythia8_events.hepmc").write_text("test hepmc\n")
                log_path.write_text("Cross-section : 1.0 +- 0.1 pb\n")
    toolchain = HepToolchainReport(True, tmp_path / "mg5_aMC", None, None, None, "test", "test")
    shower = "Main:numberOfEvents = -1\nHEPMCoutput:file = hepmc\nPartonLevel:ISR = off\n"
    detector = "# custom detector\nset ExecutionPath {}\n"
    monkeypatch.setattr("findingz.hep_pipeline.extract_delphes_dileptons", lambda path: extract_lhe_truth(generated_lhe))
    config = HepSimulationConfig(run_mode="full" if full else "madgraph", run_card_overrides={"ptl": 25.0},
                                 param_card_overrides={"mass 23": 92.0},
                                 shower_card_text=shower if full else None,
                                 detector_card_text=detector if full else None)
    run = run_hep_simulation(config, tmp_path / "runs", runner=Runner(), toolchain=toolchain)
    manifest = json.loads(run.manifest_path.read_text())
    assert manifest["status"] == "complete"
    assert manifest["config"]["run_card_overrides"] == {"ptl": 25.0}
    assert "25.0 = ptl" in (run.run_dir / "cards/generated/run_card.dat").read_text()
    assert "23  92.0" in (run.run_dir / "cards/generated/param_card.dat").read_text()
    assert "25 125." in (run.run_dir / "cards/generated/param_card.dat").read_text()
    assert manifest["config"]["param_card_overrides"] == {"mass 23": 92.0}
    if full:
        assert (run.run_dir / "cards/generated/pythia8_card.dat").read_text() == shower
        assert (run.run_dir / "cards/generated/delphes_card.dat").read_text() == detector
    assert not (run.run_dir / "process").exists()
