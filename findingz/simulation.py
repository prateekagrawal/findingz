from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from pydantic import BaseModel, Field, model_validator

from .physics import FourVector, add_observables, lorentz_boost

ChannelName = Literal["ee", "mumu"]


class ToySimulationConfig(BaseModel):
    """Validated inputs for the fast local teaching simulation."""

    name: str = Field(default="finding-z", pattern=r"^[a-zA-Z0-9_-]+$")
    label: str | None = Field(default=None, min_length=1, max_length=80)
    events: int = Field(default=2_000, ge=100, le=10_000)
    seed: int = Field(default=225, ge=0, le=2**32 - 1)
    channels: list[ChannelName] = Field(default_factory=lambda: ["ee", "mumu"])
    z_mass_gev: float = Field(default=91.1876, ge=80.0, le=100.0)
    z_width_gev: float = Field(default=2.4952, gt=0.1, le=10.0)
    continuum_fraction: float = Field(default=0.30, ge=0.0, le=0.90)
    detector_pt_resolution: float = Field(default=0.02, ge=0.0, le=0.20)
    min_mass_gev: float = Field(default=50.0, ge=10.0, le=120.0)
    max_mass_gev: float = Field(default=130.0, ge=60.0, le=500.0)

    @model_validator(mode="after")
    def validate_ranges(self) -> ToySimulationConfig:
        if not self.channels:
            raise ValueError("At least one dilepton channel is required")
        if len(set(self.channels)) != len(self.channels):
            raise ValueError("Dilepton channels must be unique")
        if self.min_mass_gev >= self.max_mass_gev:
            raise ValueError("min_mass_gev must be smaller than max_mass_gev")
        if not self.min_mass_gev < self.z_mass_gev < self.max_mass_gev:
            raise ValueError("The Z mass must lie inside the simulated mass range")
        return self


@dataclass(frozen=True)
class SimulationRun:
    run_dir: Path
    truth_path: Path
    detector_path: Path
    analysis_path: Path
    manifest_path: Path
    reused: bool


def _config_hash(config: ToySimulationConfig) -> str:
    canonical = json.dumps(
        config.model_dump(mode="json", exclude={"label"}),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:10]


def _sample_truncated_cauchy(
    rng: np.random.Generator, location: float, scale: float, low: float, high: float
) -> float:
    while True:
        value = location + scale * rng.standard_cauchy()
        if low <= value <= high:
            return float(value)


def _sample_continuum_mass(rng: np.random.Generator, low: float, high: float) -> float:
    """Sample a simple falling 1/m^2 continuum between fixed bounds."""
    uniform = rng.random()
    return float(1.0 / (1.0 / low - uniform * (1.0 / low - 1.0 / high)))


def _sample_direction(rng: np.random.Generator) -> np.ndarray:
    # Accept/reject a vector-current-inspired 1 + cos^2(theta) distribution.
    while True:
        cosine = rng.uniform(-1.0, 1.0)
        if rng.uniform(0.0, 2.0) <= 1.0 + cosine**2:
            break
    sine = math.sqrt(1.0 - cosine**2)
    phi = rng.uniform(-math.pi, math.pi)
    return np.array([sine * math.cos(phi), sine * math.sin(phi), cosine])


def _sample_boost(rng: np.random.Generator) -> tuple[float, float, float]:
    while True:
        candidate = rng.normal(0.0, [0.05, 0.05, 0.28])
        if float(candidate @ candidate) < 0.70**2:
            return tuple(float(value) for value in candidate)


def _coordinates(vector: FourVector) -> tuple[float, float, float]:
    pt = max(vector.pt, 1e-12)
    return pt, math.asinh(vector.pz / pt), math.atan2(vector.py, vector.px)


def _generate_truth(config: ToySimulationConfig) -> pd.DataFrame:
    rng = np.random.default_rng(config.seed)
    rows: list[dict[str, object]] = []
    for event_id in range(config.events):
        continuum = rng.random() < config.continuum_fraction
        if continuum:
            pair_mass = _sample_continuum_mass(rng, config.min_mass_gev, config.max_mass_gev)
            component = "continuum"
        else:
            pair_mass = _sample_truncated_cauchy(
                rng,
                config.z_mass_gev,
                config.z_width_gev / 2.0,
                config.min_mass_gev,
                config.max_mass_gev,
            )
            component = "z_resonance"

        channel = str(rng.choice(config.channels))
        flavor = "e" if channel == "ee" else "mu"
        lepton_mass = 0.000511 if flavor == "e" else 0.10566
        energy = pair_mass / 2.0
        momentum = math.sqrt(max(energy**2 - lepton_mass**2, 0.0))
        direction = _sample_direction(rng)
        first = FourVector(energy, *(momentum * direction).tolist())
        second = FourVector(energy, *(-momentum * direction).tolist())
        boost = _sample_boost(rng)
        vectors = [lorentz_boost(first, boost), lorentz_boost(second, boost)]

        row: dict[str, object] = {
            "event_id": event_id,
            "channel": channel,
            "weight": 1.0,
            "source": "toy_truth",
            "component": component,
        }
        for index, (vector, charge) in enumerate(zip(vectors, [-1, 1]), start=1):
            pt, eta, phi = _coordinates(vector)
            row.update(
                {
                    f"l{index}_pt": pt,
                    f"l{index}_eta": eta,
                    f"l{index}_phi": phi,
                    f"l{index}_mass": lepton_mass,
                    f"l{index}_charge": charge,
                    f"l{index}_flavor": flavor,
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _simulate_detector(truth: pd.DataFrame, config: ToySimulationConfig) -> pd.DataFrame:
    rng = np.random.default_rng(config.seed + 1)
    detector = truth.drop(columns=["component"]).copy()
    detector["source"] = "toy_detector"
    for index in range(1, 3):
        scale = rng.normal(1.0, config.detector_pt_resolution, len(detector))
        detector[f"l{index}_pt"] = np.maximum(detector[f"l{index}_pt"] * scale, 0.0)
        detector[f"l{index}_eta"] += rng.normal(0.0, 0.002, len(detector))
        detector[f"l{index}_phi"] += rng.normal(0.0, 0.001, len(detector))
        detector[f"l{index}_phi"] = (
            (detector[f"l{index}_phi"] + math.pi) % (2.0 * math.pi)
        ) - math.pi
    detector["accepted"] = detector[["l1_pt", "l2_pt"]].min(axis=1).ge(10.0) & detector[
        ["l1_eta", "l2_eta"]
    ].abs().max(axis=1).le(2.5)
    return detector


def _build_manifest(
    config: ToySimulationConfig, run_id: str, accepted_events: int
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "label": config.label or run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "simulation": "FindingZ fast pedagogical simulator",
        "provenance": (
            "Synthetic toy events; not MadGraph, Pythia, Delphes, detector data, "
            "or a precision Standard Model prediction."
        ),
        "config": config.model_dump(mode="json", exclude={"label"}),
        "stages": {
            "truth": "truth.csv",
            "detector": "detector.csv",
            "analysis": "analysis.csv",
        },
        "generated_events": config.events,
        "accepted_events": accepted_events,
    }


def run_toy_simulation(config: ToySimulationConfig, run_root: Path | str = "runs") -> SimulationRun:
    """Run or reuse a deterministic, checkpointed local simulation."""
    run_id = f"{config.name}-{_config_hash(config)}"
    run_dir = Path(run_root) / run_id
    truth_path = run_dir / "truth.csv"
    detector_path = run_dir / "detector.csv"
    analysis_path = run_dir / "analysis.csv"
    manifest_path = run_dir / "manifest.json"
    expected = [truth_path, detector_path, analysis_path, manifest_path]
    if all(path.exists() for path in expected):
        if config.label:
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("label") != config.label:
                manifest["label"] = config.label
                manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        return SimulationRun(
            run_dir, truth_path, detector_path, analysis_path, manifest_path, reused=True
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    if truth_path.exists():
        truth = pd.read_csv(truth_path)
    else:
        truth = _generate_truth(config)
        truth.to_csv(truth_path, index=False)

    if detector_path.exists():
        detector = pd.read_csv(detector_path)
    else:
        detector = _simulate_detector(truth, config)
        detector.to_csv(detector_path, index=False)

    accepted = detector.loc[detector["accepted"].astype(bool)].copy()
    analysis = add_observables(accepted)
    analysis.to_csv(analysis_path, index=False)
    manifest = _build_manifest(config, run_id, len(analysis))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return SimulationRun(
        run_dir, truth_path, detector_path, analysis_path, manifest_path, reused=False
    )


def make_simulation_figure(run: SimulationRun) -> Figure:
    truth = add_observables(pd.read_csv(run.truth_path))
    reconstructed = pd.read_csv(run.analysis_path)
    figure = Figure(figsize=(8, 5))
    axis = figure.subplots()
    bins = np.linspace(
        min(float(truth["mll"].min()), float(reconstructed["mll"].min())),
        max(float(truth["mll"].max()), float(reconstructed["mll"].max())),
        50,
    )
    axis.hist(truth["mll"], bins=bins, histtype="step", linewidth=2, label="truth")
    axis.hist(
        reconstructed["mll"],
        bins=bins,
        histtype="stepfilled",
        alpha=0.28,
        label="accepted + smeared",
    )
    axis.set_xlabel(r"Dilepton invariant mass $m_{\ell\ell}$ [GeV]")
    axis.set_ylabel("Toy events")
    axis.set_title("Finding Z: local pedagogical simulation")
    axis.grid(alpha=0.2)
    axis.legend()
    figure.tight_layout()
    return figure
