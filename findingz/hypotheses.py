from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from .catalog import CourseCatalog, resolve_catalog_path
from .physics import add_observables, add_ranked_lepton_observables
from .runs import list_saved_runs

SampleKind = Literal["prepared", "generated"]


@dataclass(frozen=True)
class AnalysisSample:
    sample_id: str
    label: str
    kind: SampleKind
    path: Path
    provenance: str
    config: dict[str, object]
    generated_events: int | None = None
    cross_section_pb: float | None = None

    @property
    def menu_label(self) -> str:
        return self.label

    @property
    def generated_context(self) -> tuple[object, ...] | None:
        if self.kind != "generated":
            return None
        return (
            self.config.get("collider_id", self.config.get("collider")),
            self.config.get("beam_energy_gev"),
            self.config.get("run_mode"),
            self.config.get("detector_id"),
            self.config.get("output_detail"),
            self.config.get("min_mass_gev"),
            self.config.get("max_mass_gev"),
        )

    @property
    def analysis_context(self) -> tuple[object, ...]:
        """Configuration boundary within which distributions may be compared."""
        if self.kind == "prepared":
            return ("legacy-synthetic-z",)
        context = self.generated_context
        if context is None:  # pragma: no cover - guarded by the sample kind
            raise ValueError(f"Generated sample {self.label} has no analysis context")
        return context

    @property
    def analysis_context_label(self) -> str:
        if self.kind == "prepared":
            return "Legacy synthetic Z exercise (not collider simulation)"
        collider, beam_energy, run_mode, detector, output, low_mass, high_mass = (
            self.analysis_context
        )
        energy = (
            f"√s = {2 * float(beam_energy):g} GeV"
            if isinstance(beam_energy, int | float)
            else "energy unknown"
        )
        level = "full detector pipeline" if run_mode == "full" else "MadGraph parton level"
        detector_text = f" · {detector}" if detector not in {None, "none"} else ""
        output_text = f" · {output} output" if output not in {None, "standard"} else ""
        mass_text = (
            f" · generated mll {float(low_mass):g}–{float(high_mass):g} GeV"
            if isinstance(low_mass, int | float) and isinstance(high_mass, int | float)
            else ""
        )
        collider_label = self.config.get("collider_label", collider)
        return (
            f"{collider_label} · {energy} · {level}"
            f"{detector_text}{output_text}{mass_text}"
        )

    def load(self) -> pd.DataFrame:
        frame = pd.read_csv(self.path)
        frame = frame if "mll" in frame.columns else add_observables(frame)
        return add_ranked_lepton_observables(frame)

    def expected_frame(self, luminosity_fb: float) -> pd.DataFrame:
        frame = self.load().copy()
        if "weight" not in frame:
            frame["weight"] = 1.0
        if self.kind == "prepared":
            return frame
        if not self.generated_events or self.cross_section_pb is None:
            raise ValueError(
                f"{self.label} has no MadGraph cross section and cannot be normalized "
                "to an expected yield"
            )
        frame["weight"] = (
            pd.to_numeric(frame["weight"], errors="raise")
            * self.cross_section_pb
            * luminosity_fb
            * 1_000.0
            / self.generated_events
        )
        return frame


def build_sample_library(
    catalog: CourseCatalog, run_root: Path | str
) -> dict[str, AnalysisSample]:
    samples: dict[str, AnalysisSample] = {}
    # Instructor samples are ordinary complete runs, not separately normalized CSVs.
    runs = {}
    labels = {}
    for entry in catalog.available_datasets().values():
        directory = resolve_catalog_path(entry.path)
        if not directory.is_dir():
            continue  # Legacy synthetic CSVs remain usable by the old notebooks only.
        for run in list_saved_runs(directory.parent):
            if run.manifest_path.parent == directory:
                runs[run.run_id] = run
                labels[run.run_id] = entry.label
    for run in list_saved_runs(run_root):
        runs[run.run_id] = run

    for run in runs.values():
        manifest = json.loads(run.manifest_path.read_text())
        config = manifest.get("config")
        config = dict(config) if isinstance(config, dict) else {}
        beam_type = config.get("collider")
        beam_energy = config.get("beam_energy_gev")
        collider_id = config.get("collider_id")
        collider = catalog.colliders.get(str(collider_id)) if collider_id else None
        if collider is None:
            collider_match = next(
                (
                    (entry_id, entry)
                    for entry_id, entry in catalog.colliders.items()
                    if entry.beam_type == beam_type
                    and isinstance(beam_energy, int | float)
                    and abs(entry.beam_energy_gev - float(beam_energy)) < 1e-6
                ),
                None,
            )
            if collider_match is not None:
                collider_id, collider = collider_match
                config["collider_id"] = collider_id
        if collider is not None:
            config["collider_label"] = collider.label
        if config.get("run_mode") == "full":
            config.setdefault(
                "detector_id", collider.default_detector_id if collider is not None else None
            )
        else:
            config.setdefault("detector_id", "none")
        config.setdefault("output_detail", "standard")
        cross_section = manifest.get("cross_section_pb")
        samples[f"run:{run.run_id}"] = AnalysisSample(
            sample_id=f"run:{run.run_id}",
            label=labels.get(run.run_id, run.label),
            kind="generated",
            path=run.analysis_path,
            provenance=str(manifest.get("provenance", "")),
            config=config,
            generated_events=run.generated_events,
            cross_section_pb=(
                float(cross_section) if isinstance(cross_section, int | float) else None
            ),
        )
    return samples


def select_events(
    frame: pd.DataFrame,
    *,
    channels: list[str],
    minimum_pt: float,
    maximum_abs_eta: float,
    mass_window: tuple[float, float] | None = None,
) -> pd.DataFrame:
    selected = frame.loc[
        frame["channel"].isin(channels)
        & frame[["l1_pt", "l2_pt"]].min(axis=1).ge(minimum_pt)
        & frame[["l1_eta", "l2_eta"]].abs().max(axis=1).le(maximum_abs_eta)
    ]
    if mass_window is not None:
        selected = selected.loc[selected["mll"].between(*mass_window)]
    return selected.copy()


def validate_analysis_context(samples: list[AnalysisSample]) -> None:
    if not samples:
        raise ValueError("Choose at least one analysis sample")
    if len({sample.analysis_context for sample in samples}) != 1:
        raise ValueError(
            "All plotted hypotheses must use the same collider and simulation configuration"
        )


def compatible_counting_backgrounds(
    signal: AnalysisSample, library: dict[str, AnalysisSample]
) -> list[str]:
    """Use the same checks for menu eligibility and execution."""
    compatible = []
    for sample_id, sample in library.items():
        if sample.sample_id == signal.sample_id:
            continue
        try:
            validate_counting_samples([signal, sample])
        except ValueError:
            continue
        compatible.append(sample_id)
    return compatible


def validate_counting_samples(samples: list[AnalysisSample]) -> None:
    if not samples:
        raise ValueError("Choose at least one signal or background sample")
    kinds = {sample.kind for sample in samples}
    if len(kinds) != 1:
        raise ValueError(
            "A count cannot mix prepared teaching templates with generated runs; "
            "use samples with a common normalization"
        )
    if kinds == {"generated"}:
        contexts = {sample.generated_context for sample in samples}
        if len(contexts) != 1:
            fields = ["collider", "beam energy [GeV]", "simulation level", "detector",
                      "output profile", "generated mass minimum [GeV]",
                      "generated mass maximum [GeV]"]
            details = []
            readable = {"full": "MadGraph + Pythia + Delphes",
                        "madgraph": "MadGraph only (parton level)", "none": "no detector"}
            for index, field in enumerate(fields):
                if len({sample.generated_context[index] for sample in samples}) > 1:
                    values = "; ".join(
                        f"{sample.label}: "
                        f"{readable.get(str(sample.generated_context[index]), sample.generated_context[index])}"
                        for sample in samples
                    )
                    details.append(f"{field} ({values})")
            raise ValueError(
                "Generated signal and background runs must use the same collider, energy, "
                "simulation level, detector configuration, output profile, and generated mass range. "
                "Differences: " + "; ".join(details)
            )
        missing = [
            sample.label
            for sample in samples
            if not sample.generated_events or sample.cross_section_pb is None
        ]
        if missing:
            raise ValueError(f"Generated samples lack cross-section normalization: {missing}")
