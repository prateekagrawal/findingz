import json

import pytest

from findingz.delphes import list_runs, open_run


def test_list_runs_returns_only_completed_delphes_checkpoints(tmp_path) -> None:
    complete = tmp_path / "finding-z-hep-complete"
    complete.joinpath("detector").mkdir(parents=True)
    complete.joinpath("detector", "delphes.root").write_text("root checkpoint")
    complete.joinpath("manifest.json").write_text(
        json.dumps(
            {
                "run_id": complete.name,
                "status": "complete",
                "generated_events": 100,
                "config": {"process": "dy_ll", "collider": "pp", "detector": "standard"},
                "stages": {"detector_root": "detector/delphes.root"},
            }
        )
    )
    failed = tmp_path / "finding-z-hep-failed"
    failed.mkdir()
    failed.joinpath("manifest.json").write_text(json.dumps({"status": "failed"}))

    runs = list_runs(tmp_path)

    assert runs["run_id"].tolist() == [complete.name]
    assert runs.iloc[0]["detector"] == "standard"
    assert runs.iloc[0]["output_detail"] == "standard"


def test_open_run_rejects_path_traversal(tmp_path) -> None:
    with pytest.raises(ValueError, match="letters, digits"):
        open_run("../outside", tmp_path)
