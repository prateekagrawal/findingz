from pathlib import Path

import pytest

from findingz.hep_pipeline import (
    HepSimulationConfig,
    HepToolchainReport,
    hep_run_directory,
    render_madevent_commands,
    resolve_detector_card,
)


def stack(root):
    return HepToolchainReport(True, root / "MG5/bin/mg5_aMC", root,
                              root / "bin", None, "cit-test", "test")


def test_conda_split_card_layout_and_content_identity(tmp_path, monkeypatch):
    card = tmp_path / "cards/delphes_card_CMS.tcl"
    card.parent.mkdir()
    card.write_text("set ExecutionPath {}\n")
    monkeypatch.setenv("FINDINGZ_CARD_ROOT", str(tmp_path))
    config = HepSimulationConfig()
    assert resolve_detector_card(config, stack(tmp_path)) == card
    before = hep_run_directory(config, tmp_path / "runs", "cit-test")
    card.write_text("set ExecutionPath {ParticlePropagator}\n")
    assert hep_run_directory(config, tmp_path / "runs", "cit-test") != before


def test_explicit_missing_card_does_not_fall_back(tmp_path, monkeypatch):
    monkeypatch.setenv("FINDINGZ_CARD_ROOT", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="not found"):
        resolve_detector_card(HepSimulationConfig(), stack(tmp_path))


def test_card_symlink_escape_rejected(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "cards").mkdir(parents=True)
    target = tmp_path / "outside.tcl"
    target.write_text("set ExecutionPath {}\n")
    (root / "cards/delphes_card_CMS.tcl").symlink_to(target)
    monkeypatch.setenv("FINDINGZ_CARD_ROOT", str(root))
    with pytest.raises(RuntimeError, match="escapes"):
        resolve_detector_card(HepSimulationConfig(), stack(root))


def test_default_event_count():
    config = HepSimulationConfig()
    assert config.events == 1000
    assert "set nevents 1000" in render_madevent_commands(config, "run_01")


def test_packaged_defaults_have_no_external_demo_datasets():
    from findingz.catalog import load_catalog

    path = Path(__file__).parents[1] / "findingz/resources/config/course_catalog.yaml"
    assert not load_catalog(path).datasets
