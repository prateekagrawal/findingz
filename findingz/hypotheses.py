from __future__ import annotations

from .beams import com_energy

import json
import math
import re
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
            tuple(sorted(self.config.get("run_card_overrides", {}).items())),
            self._card_digest("shower_card_text"),
            self._card_digest("detector_card_text"),
        )

    def _card_digest(self, field: str) -> str | None:
        from hashlib import sha256
        text = self.config.get(field)
        return sha256(text.encode()).hexdigest() if text is not None else None

    @property
    def analysis_context(self) -> tuple[object, ...]:
        """Only the collision setup and analysis level are hard compatibility boundaries."""
        if self.kind == "prepared":
            return ("legacy-synthetic-z",)
        context = self.generated_context
        if context is None:  # pragma: no cover - guarded by the sample kind
            raise ValueError(f"Generated sample {self.label} has no analysis context")
        return (self.config.get("collider", context[0]), context[1], context[2],
                self.config.get("beam2_energy_gev") or context[1])

    @property
    def analysis_context_label(self) -> str:
        if self.kind == "prepared":
            return "Legacy synthetic Z exercise (not collider simulation)"
        collider, beam_energy, run_mode, detector, output, low_mass, high_mass, run_card, shower_hash, detector_hash = (
            self.generated_context
        )
        energy = (
            f"√s = {com_energy(float(beam_energy), self.config.get('beam2_energy_gev')):g} GeV"
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
        card_text = " · run card: " + ", ".join(f"{k}={v}" for k, v in run_card) if run_card else ""
        if shower_hash:
            card_text += f" · custom shower {shower_hash[:8]}"
        if detector_hash:
            card_text += f" · custom detector {detector_hash[:8]}"
        return (
            f"{collider_label} · {energy} · {level}"
            f"{detector_text}{output_text}{mass_text}{card_text}"
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
    for folder in catalog.dataset_folders.values():
        if not folder.is_available():
            continue
        directory = resolve_catalog_path(folder.path, catalog._source)
        if not directory.is_dir():
            raise ValueError(f"Shared dataset folder is unavailable: {directory}")
        for manifest_path in directory.glob("*/manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("schema_version", 1) not in (1, 2):
                raise ValueError(f"Unsupported FindingZ dataset schema in {manifest_path}; update FindingZ or use compatible samples")
        for run in list_saved_runs(directory):
            if run.run_id in runs and runs[run.run_id].manifest_path != run.manifest_path:
                raise ValueError(f"Duplicate shared dataset run ID: {run.run_id}")
            runs[run.run_id] = run
    for entry in catalog.available_datasets().values():
        directory = resolve_catalog_path(entry.path, catalog._source)
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
                    and (entry.beam2_energy_gev or entry.beam_energy_gev)
                    == (config.get("beam2_energy_gev") or beam_energy)
                ),
                None,
            )
            if collider_match is not None:
                collider_id, collider = collider_match
                config["collider_id"] = collider_id
        if collider is not None:
            config["collider_label"] = collider.label
            config.setdefault("collider", collider.beam_type)
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


def _generation_settings(sample: AnalysisSample) -> tuple[dict[str, str], bool]:
    """Compare saved effective values generically, without classifying individual cuts."""
    path = sample.path.parent / "cards/generated/run_card.dat"
    settings = {}
    try:
        for line in path.read_text().splitlines():
            active = re.split(r"[!#]", line, maxsplit=1)[0]
            if active.count("=") == 1:
                value, name = active.split("=")
                settings[name.strip().lower()] = value.strip()
        complete = bool(settings)
    except OSError:
        complete = False
    if not complete:
        settings = dict(sample.config.get("run_card_overrides", {}))
        for field, name in (("min_mass_gev", "mmll"), ("max_mass_gev", "mmllmax")):
            if sample.config.get(field) is not None:
                settings[name] = sample.config[field]
    # Sampling statistics and output labels do not define the physical prediction.
    for name in ("nevents", "iseed", "run_tag"):
        settings.pop(name, None)
    normalized = {}
    for name, value in settings.items():
        text = str(value).strip().lower()
        try:
            normalized[name] = format(float(text.replace("d", "e")), ".12g")
        except ValueError:
            normalized[name] = " ".join(text.split())
    return normalized, complete


def _effective_card(sample: AnalysisSample, filename: str, config_field: str):
    try:
        text = (sample.path.parent / "cards/generated" / filename).read_text()
    except OSError:
        text = sample.config.get(config_field)
    if text is None:
        return None
    # Comments and formatting alone should not produce a warning.
    lines = ((line.strip() if not line.lstrip().startswith("#") else "")
             if filename == "delphes_card.dat" else re.split(r"[!#]", line, maxsplit=1)[0].strip()
             for line in text.splitlines())
    return "\n".join(" ".join(line.split()) for line in lines if line)


def compatibility_warnings(samples: list[AnalysisSample]) -> list[str]:
    """Nonblocking differences, not a certification of matching phase-space coverage."""
    generated = [sample for sample in samples if sample.kind == "generated"]
    if len(generated) < 2:
        return []
    reports = []
    settings = [_generation_settings(sample) for sample in generated]
    names = set().union(*(values.keys() for values, _ in settings))
    changed = sorted(name for name in names if len({values.get(name) for values, _ in settings}) > 1)
    if changed:
        reports.append("Generation settings differ (" + ", ".join(changed) + "). "
                       "Check cut coverage and PDF/scale choices before interpreting the comparison.")
    for label, filename, field in (("Shower", "pythia8_card.dat", "shower_card_text"),
                                   ("Detector", "delphes_card.dat", "detector_card_text")):
        cards = [_effective_card(sample, filename, field) for sample in generated]
        if len(set(cards)) > 1:
            reports.append(f"{label} cards differ or are unavailable for some samples.")
    for field, label in (("detector_id", "Detector presets"), ("output_detail", "Output profiles")):
        if len({sample.config.get(field) for sample in generated}) > 1:
            reports.append(f"{label} differ; check that the selected objects represent the same measurement.")
    if any(not complete for _, complete in settings):
        reports.append("Saved generation cards are missing for some samples; PDF, scale and cut agreement is not fully checked.")
    return reports


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
        contexts = {sample.analysis_context for sample in samples}
        if len(contexts) != 1:
            fields = ["collider", "beam energy [GeV]", "simulation level"]
            details = []
            readable = {"full": "MadGraph + Pythia + Delphes",
                        "madgraph": "MadGraph only (parton level)", "none": "no detector"}
            for index, field in enumerate(fields):
                if len({sample.analysis_context[index] for sample in samples}) > 1:
                    values = "; ".join(
                        f"{sample.label}: "
                        f"{readable.get(str(sample.analysis_context[index]), sample.analysis_context[index])}"
                        for sample in samples
                    )
                    details.append(f"{field} ({values})")
            raise ValueError(
                "Generated signal and background runs must use the same collider, energy, "
                "and simulation level. "
                "Differences: " + "; ".join(details)
            )
        missing = [
            sample.label
            for sample in samples
            if (not sample.generated_events or sample.generated_events <= 0
                or sample.cross_section_pb is None or not math.isfinite(sample.cross_section_pb)
                or sample.cross_section_pb < 0)
        ]
        if missing:
            raise ValueError(f"Generated samples lack cross-section normalization: {missing}")
