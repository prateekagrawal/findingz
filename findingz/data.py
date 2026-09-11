from __future__ import annotations

from pathlib import Path

import pandas as pd

from .catalog import load_catalog, resolve_catalog_path

DATA_FILENAMES = {
    "signal": "signal.csv",
    "background": "background.csv",
    "collision": "collision.csv",
}
REQUIRED_COLUMNS = {
    "event_id",
    "channel",
    "weight",
    "source",
    *{
        f"l{i}_{field}"
        for i in range(1, 3)
        for field in ("pt", "eta", "phi", "mass", "charge", "flavor")
    },
}


def default_data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data"


def load_sample(sample: str, data_dir: Path | None = None) -> pd.DataFrame:
    if data_dir is not None:
        if sample not in DATA_FILENAMES:
            raise ValueError(f"Unsupported sample: {sample}")
        path = data_dir / DATA_FILENAMES[sample]
    else:
        datasets = load_catalog().available_datasets()
        if sample not in datasets:
            raise ValueError(f"Unavailable or unsupported sample: {sample}")
        path = resolve_catalog_path(datasets[sample].path)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run `python scripts/generate_demo_data.py` from the project root."
        )
    frame = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {sorted(missing)}")
    if not frame["channel"].isin(["ee", "mumu"]).all():
        raise ValueError(f"{path.name} contains an unsupported dilepton channel")
    opposite_sign = (frame["l1_charge"] + frame["l2_charge"]).eq(0)
    same_flavor = frame["l1_flavor"].eq(frame["l2_flavor"])
    channel_consistent = (frame["channel"].eq("ee") & frame["l1_flavor"].eq("e")) | (
        frame["channel"].eq("mumu") & frame["l1_flavor"].eq("mu")
    )
    if not (opposite_sign & same_flavor & channel_consistent).all():
        raise ValueError(f"{path.name} must contain opposite-sign same-flavor dileptons")
    frame["sample"] = sample
    return frame


def describe_sample(sample: str, data_dir: Path | None = None) -> dict[str, object]:
    frame = load_sample(sample, data_dir)
    provenance = None
    if data_dir is None:
        provenance = load_catalog().available_datasets()[sample].provenance
    return {
        "sample": sample,
        "events": len(frame),
        "channels": sorted(frame["channel"].unique().tolist()),
        "units": {"energy": "GeV", "angles": "radians"},
        "source": provenance
        or ("synthetic teaching data" if frame["source"].eq("synthetic").all() else "prepared"),
    }
