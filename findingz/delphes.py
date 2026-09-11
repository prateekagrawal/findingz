from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

_RUN_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_COLLECTIONS: dict[str, tuple[str, dict[str, str], float | None]] = {
    "electrons": (
        "Electron",
        {"pt": "PT", "eta": "Eta", "phi": "Phi", "charge": "Charge", "isolation": "IsolationVar"},
        0.000511,
    ),
    "muons": (
        "Muon",
        {"pt": "PT", "eta": "Eta", "phi": "Phi", "charge": "Charge", "isolation": "IsolationVar"},
        0.10566,
    ),
    "photons": (
        "Photon",
        {"pt": "PT", "eta": "Eta", "phi": "Phi", "isolation": "IsolationVar"},
        0.0,
    ),
    "jets": (
        "Jet",
        {"pt": "PT", "eta": "Eta", "phi": "Phi", "mass": "Mass", "btag": "BTag", "tautag": "TauTag"},
        None,
    ),
    "fat_jets": (
        "FatJet",
        {"pt": "PT", "eta": "Eta", "phi": "Phi", "mass": "Mass"},
        None,
    ),
    "missing_et": ("MissingET", {"met": "MET", "eta": "Eta", "phi": "Phi"}, None),
    "scalar_ht": ("ScalarHT", {"ht": "HT"}, None),
    "gen_jets": (
        "GenJet",
        {"pt": "PT", "eta": "Eta", "phi": "Phi", "mass": "Mass"},
        None,
    ),
    "gen_missing_et": ("GenMissingET", {"met": "MET", "eta": "Eta", "phi": "Phi"}, None),
    "particles": (
        "Particle",
        {
            "pid": "PID",
            "status": "Status",
            "charge": "Charge",
            "mass": "Mass",
            "energy": "E",
            "px": "Px",
            "py": "Py",
            "pz": "Pz",
            "pt": "PT",
            "eta": "Eta",
            "phi": "Phi",
        },
        None,
    ),
    "tracks": (
        "Track",
        {"pid": "PID", "charge": "Charge", "pt": "PT", "eta": "Eta", "phi": "Phi"},
        None,
    ),
    "towers": ("Tower", {"et": "ET", "eta": "Eta", "phi": "Phi", "energy": "E"}, None),
    "eflow_tracks": (
        "EFlowTrack",
        {"pid": "PID", "charge": "Charge", "pt": "PT", "eta": "Eta", "phi": "Phi"},
        None,
    ),
    "eflow_photons": (
        "EFlowPhoton",
        {"et": "ET", "eta": "Eta", "phi": "Phi", "energy": "E"},
        None,
    ),
    "eflow_neutral_hadrons": (
        "EFlowNeutralHadron",
        {"et": "ET", "eta": "Eta", "phi": "Phi", "energy": "E"},
        None,
    ),
}


def default_run_root() -> Path:
    configured = os.environ.get("FINDINGZ_RUN_ROOT")
    return Path(configured).expanduser().resolve() if configured else Path("runs").resolve()


@dataclass
class DelphesEvents:
    """Lazy, Awkward-backed access to the object collections in one Delphes run."""

    path: Path
    manifest: dict[str, object]
    _root_file: Any = field(repr=False)
    _tree: Any = field(repr=False)
    _cache: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def event_count(self) -> int:
        return int(self._tree.num_entries)

    @property
    def available_collections(self) -> tuple[str, ...]:
        return tuple(
            alias
            for alias, (branch, fields, _) in _COLLECTIONS.items()
            if any(self._has_branch(f"{branch}.{field_name}") for field_name in fields.values())
        )

    def _has_branch(self, name: str) -> bool:
        try:
            self._tree[name]
        except KeyError:
            return False
        return True

    def collection(self, alias: str) -> Any:
        """Load one named collection as a jagged Awkward record array."""
        if alias not in _COLLECTIONS:
            raise KeyError(f"Unknown collection {alias!r}; choose from {sorted(_COLLECTIONS)}")
        if alias in self._cache:
            return self._cache[alias]

        try:
            import awkward as ak
            import vector
        except ImportError as error:
            raise RuntimeError(
                "Delphes object analysis requires the 'hep' dependencies: awkward and vector"
            ) from error

        vector.register_awkward()
        branch, requested_fields, fixed_mass = _COLLECTIONS[alias]
        data = {
            field_alias: self._tree[f"{branch}.{field_name}"].array(library="ak")
            for field_alias, field_name in requested_fields.items()
            if self._has_branch(f"{branch}.{field_name}")
        }
        if not data:
            raise KeyError(
                f"Collection {branch} is not stored in {self.path.name}; "
                "use the advanced detector profile for low-level objects"
            )
        if fixed_mass is not None and "pt" in data:
            data["mass"] = ak.full_like(data["pt"], fixed_mass)
        vector_fields = {"pt", "eta", "phi", "mass"}
        with_name = "Momentum4D" if vector_fields.issubset(data) else None
        result = ak.zip(data, with_name=with_name)
        self._cache[alias] = result
        return result

    def __getitem__(self, alias: str) -> Any:
        return self.collection(alias)

    @property
    def electrons(self) -> Any:
        return self.collection("electrons")

    @property
    def muons(self) -> Any:
        return self.collection("muons")

    @property
    def photons(self) -> Any:
        return self.collection("photons")

    @property
    def jets(self) -> Any:
        return self.collection("jets")

    @property
    def fat_jets(self) -> Any:
        return self.collection("fat_jets")

    @property
    def missing_et(self) -> Any:
        return self.collection("missing_et")

    @property
    def scalar_ht(self) -> Any:
        return self.collection("scalar_ht")


def list_runs(run_root: Path | str | None = None) -> pd.DataFrame:
    """List completed runs that retain a Delphes ROOT checkpoint."""
    root = Path(run_root).resolve() if run_root is not None else default_run_root()
    rows: list[dict[str, object]] = []
    if not root.exists():
        return pd.DataFrame()
    for manifest_path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        stages = manifest.get("stages", {})
        if manifest.get("status") != "complete" or not isinstance(stages, dict):
            continue
        root_relative = stages.get("detector_root")
        if not isinstance(root_relative, str) or not (manifest_path.parent / root_relative).exists():
            continue
        config = manifest.get("config", {})
        config = config if isinstance(config, dict) else {}
        rows.append(
            {
                "run_id": manifest.get("run_id", manifest_path.parent.name),
                "events": manifest.get("generated_events"),
                "process": config.get("process"),
                "collider": config.get("collider"),
                "detector": config.get("detector_id", config.get("detector", "legacy")),
                "output_detail": config.get("output_detail", config.get("detector", "legacy")),
                "root_path": str((manifest_path.parent / root_relative).resolve()),
            }
        )
    return pd.DataFrame(rows)


def open_run(run_id: str, run_root: Path | str | None = None) -> DelphesEvents:
    """Open a completed Finding Z run by its manifest run ID."""
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id may contain letters, digits, underscores, and hyphens only")
    root = Path(run_root).resolve() if run_root is not None else default_run_root()
    run_dir = root / run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Run manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") != "complete":
        raise RuntimeError(f"Run {run_id} is not complete")
    stages = manifest.get("stages")
    if not isinstance(stages, dict) or not isinstance(stages.get("detector_root"), str):
        raise TypeError(f"Run {run_id} does not contain a Delphes ROOT checkpoint")
    root_path = (run_dir / stages["detector_root"]).resolve()
    if not root_path.is_relative_to(run_dir.resolve()) or not root_path.exists():
        raise RuntimeError(f"Invalid or missing Delphes ROOT checkpoint for {run_id}")
    try:
        import uproot
    except ImportError as error:
        raise RuntimeError(
            "Delphes object analysis requires the 'hep' dependencies: uproot and awkward"
        ) from error
    root_file = uproot.open(root_path)
    return DelphesEvents(root_path, manifest, root_file, root_file["Delphes"])
