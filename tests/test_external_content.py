import json
from pathlib import Path

import pytest
import yaml

from findingz.catalog import ModelEntry, load_catalog
from findingz.external_models import ufo_digest
from findingz.hep_pipeline import HepSimulationConfig, hep_run_directory, render_madgraph_process_card
from findingz.hypotheses import build_sample_library


def make_ufo(root):
    root.mkdir()
    for name in ("__init__", "particles", "parameters", "vertices", "couplings", "object_library"):
        (root / f"{name}.py").write_text("# test fixture; not imported\n")
    return root


def test_model_source_is_unambiguous():
    assert ModelEntry(label="External", ufo_path="../models/x").madgraph_name is None
    for args in ({}, {"ufo_path": "x", "madgraph_name": "sm"}):
        with pytest.raises(ValueError, match="exactly one"):
            ModelEntry(label="Bad", **args)


def test_model_contents_affect_reuse(tmp_path):
    model = make_ufo(tmp_path / "ufo")
    config = HepSimulationConfig(model_ufo_path=str(model), run_mode="madgraph")
    first = hep_run_directory(config, tmp_path / "runs", "test")
    (model / "parameters.py").write_text("# revised mass\n")
    assert first != hep_run_directory(config, tmp_path / "runs", "test")
    digest = ufo_digest(model)
    (model / "__pycache__").mkdir()
    (model / "__pycache__/ignored.pyc").write_bytes(b"cache")
    assert ufo_digest(model) == digest
    card = render_madgraph_process_card(config, Path("/run/process"), Path("/run/ufo_model"))
    assert "import model /run/ufo_model\n" in card


def test_incomplete_models_and_command_injection_fail(tmp_path):
    with pytest.raises(ValueError, match="Incomplete UFO"):
        ufo_digest(tmp_path)
    config = HepSimulationConfig(model_ufo_path="/tmp/ufo\nquit", run_mode="madgraph")
    with pytest.raises(ValueError, match="command characters"):
        render_madgraph_process_card(config, tmp_path)


def test_relative_shared_folders_and_schema_guard(tmp_path):
    shared = tmp_path / "shared" / "run-a"
    shared.mkdir(parents=True)
    (shared / "analysis.csv").write_text("mll,weight\n91,1\n")
    manifest = {"schema_version": 2, "run_id": "run-a", "status": "complete",
                "label": "Shared prediction", "generated_events": 1, "cross_section_pb": 2,
                "config": {"run_mode": "madgraph"}, "stages": {"analysis": "analysis.csv"}}
    (shared / "manifest.json").write_text(json.dumps(manifest))
    payload = load_catalog().model_dump(mode="json")
    payload["datasets"] = {}
    payload["dataset_folders"] = {"shared": {"path": "shared"}}
    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(payload))
    catalog = load_catalog(path)
    library = build_sample_library(catalog, tmp_path / "personal")
    assert library["run:run-a"].label == "Shared prediction"
    assert library["run:run-a"].expected_frame(1).weight.sum() == 2000
    manifest["schema_version"] = 999
    (shared / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unsupported FindingZ dataset schema"):
        build_sample_library(catalog, tmp_path / "personal")
    catalog.dataset_folders["shared"].enabled = False
    assert build_sample_library(catalog, tmp_path / "personal") == {}


def test_catalog_minimum_version(tmp_path):
    payload = load_catalog().model_dump(mode="json")
    payload["minimum_findingz_version"] = "999.0.0"
    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="requires FindingZ"):
        load_catalog(path)
