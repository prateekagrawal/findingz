import json

from findingz.runs import list_saved_runs, saved_run


def _write_run(root, run_id: str, *, status: str | None = None, label: str | None = None):
    run_dir = root / run_id
    run_dir.mkdir()
    (run_dir / "analysis.csv").write_text("event_id,mll\n1,91\n")
    manifest = {
        "run_id": run_id,
        "label": label,
        "created_at": "2026-09-03T12:00:00+00:00",
        "generated_events": 100,
        "config": {"run_mode": "madgraph"},
        "pipeline": "MadGraph",
        "stages": {"analysis": "analysis.csv"},
    }
    if status is not None:
        manifest["status"] = status
    (run_dir / "manifest.json").write_text(json.dumps(manifest))


def test_list_saved_runs_includes_complete_legacy_and_labeled_runs(tmp_path) -> None:
    _write_run(tmp_path, "complete-run", status="complete", label="My scan")
    _write_run(tmp_path, "legacy-toy")
    _write_run(tmp_path, "failed-run", status="failed")

    runs = list_saved_runs(tmp_path)
    assert {run.run_id for run in runs} == {"complete-run", "legacy-toy"}
    selected = saved_run("complete-run", tmp_path)
    assert selected.label == "My scan"
    assert selected.run_type == "MadGraph only"
    assert "100 events" in selected.menu_label


def test_list_saved_runs_rejects_unsafe_or_missing_analysis_paths(tmp_path) -> None:
    _write_run(tmp_path, "safe-run", status="complete")
    manifest_path = tmp_path / "safe-run" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["stages"]["analysis"] = "../../outside.csv"
    manifest_path.write_text(json.dumps(manifest))

    assert list_saved_runs(tmp_path) == []
