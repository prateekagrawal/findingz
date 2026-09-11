"""Resolve duplicate submissions without silently changing existing samples."""
import json
import secrets
from pathlib import Path

from .hep_pipeline import HepSimulationConfig, hep_run_directory
from .runs import list_saved_runs
from .simulation import _config_hash


def config_directory(config, root: Path, image_id: str) -> Path:
    if isinstance(config, HepSimulationConfig):
        return hep_run_directory(config, root, image_id)
    return root / f"{config.name}-{_config_hash(config)}"


def matching_run(config, root: Path, image_id: str):
    directory = config_directory(config, root, image_id)
    return next((run for run in list_saved_runs(root)
                 if run.manifest_path.parent == directory.resolve()), None)


def fresh_config(config, root: Path, image_id: str):
    for _ in range(100):
        seed = secrets.randbelow(900_000_000) + 1
        candidate = config.model_copy(update={"seed": seed})
        if seed != config.seed and not config_directory(candidate, root, image_id).exists():
            return candidate
    raise RuntimeError("Could not choose an unused random seed; please try again")


def rename_saved_run(path: Path, label: str) -> None:
    label = label.strip()
    if not label or len(label) > 80:
        raise ValueError("Run name must contain 1–80 characters")
    manifest = json.loads(path.read_text())
    manifest["label"] = label
    temporary = path.with_suffix(".rename.tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(path)
