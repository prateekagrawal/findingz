from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from .generator_details import retain_generator_details
from .physics import add_observables
from .simulation import SimulationRun

HepCollider = Literal["pp", "ee"]
HepRunMode = Literal["madgraph", "full"]
DetectorProfile = Literal["standard", "advanced"]
MAX_HEP_EVENTS = 10_000
ProgressCallback = Callable[[str, float], None]


class HepSimulationConfig(BaseModel):
    """Bounded inputs for the containerized MadGraph/Pythia/Delphes workflow."""

    name: str = Field(default="finding-z-hep", pattern=r"^[a-zA-Z0-9_-]+$")
    label: str | None = Field(default=None, min_length=1, max_length=80)
    events: int = Field(default=1_000, ge=100, le=MAX_HEP_EVENTS)
    seed: int = Field(default=225, ge=1, le=900_000_000)
    collider_id: str = Field(default="custom", pattern=r"^[A-Za-z0-9_-]+$")
    collider: HepCollider = "pp"
    model: str = Field(default="sm", pattern=r"^[A-Za-z0-9_+-]+$")
    process: str = Field(default="dy_ll", pattern=r"^[A-Za-z0-9_-]+$")
    process_lines: list[str] = Field(default_factory=list, max_length=8)
    run_mode: HepRunMode = "full"
    beam_energy_gev: float = Field(default=6_500.0, ge=10.0, le=50_000.0)
    min_mass_gev: float = Field(default=50.0, ge=10.0, le=200.0)
    max_mass_gev: float = Field(default=130.0, ge=20.0, le=1_000.0)
    detector_id: str = Field(default="cms", pattern=r"^[A-Za-z0-9_-]+$")
    detector_card: str = Field(default="cards/delphes_card_CMS.tcl", min_length=1)
    output_detail: DetectorProfile = "standard"

    @model_validator(mode="after")
    def validate_mass_window(self) -> HepSimulationConfig:
        if self.min_mass_gev >= self.max_mass_gev:
            raise ValueError("min_mass_gev must be smaller than max_mass_gev")
        detector_path = Path(self.detector_card)
        if detector_path.is_absolute() or ".." in detector_path.parts:
            raise ValueError("detector_card must be a safe path relative to the card root")
        for index, line in enumerate(self.process_lines):
            expected = "generate " if index == 0 else "add process "
            if not line.startswith(expected):
                raise ValueError(f"process line {index + 1} must start with {expected!r}")
            if any(token in line for token in ("\n", "\r", ";", "output ", "import ", "quit")):
                raise ValueError("process_lines may contain MadGraph process definitions only")
        return self


@dataclass(frozen=True)
class HepToolchainReport:
    available: bool
    mg5_executable: Path | None
    pythia8_dir: Path | None
    delphes_dir: Path | None
    delphes_card: Path | None
    image_id: str
    detail: str


class CommandRunner(Protocol):
    def run(self, argv: list[str], *, cwd: Path, log_path: Path, timeout_s: int) -> None: ...


class SubprocessRunner:
    def run(self, argv: list[str], *, cwd: Path, log_path: Path, timeout_s: int) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w") as log:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        if completed.returncode:
            raise RuntimeError(
                f"Command failed with exit code {completed.returncode}; see {log_path}"
            )


def _first_existing(candidates: list[Path]) -> Path | None:
    return next((path for path in candidates if path.exists()), None)


def probe_hep_toolchain() -> HepToolchainReport:
    mg5_from_path = shutil.which("mg5_aMC")
    mg5 = _first_existing(
        [
            Path(os.environ["FINDINGZ_MG5"])
            if os.environ.get("FINDINGZ_MG5")
            else Path("/__missing_mg5__"),
            Path(mg5_from_path) if mg5_from_path else Path("/__missing_mg5_path__"),
            Path("/opt/hep/mg5/bin/mg5_aMC"),
        ]
    )
    pythia = _first_existing(
        [
            Path(os.environ["FINDINGZ_PYTHIA8_DIR"])
            if os.environ.get("FINDINGZ_PYTHIA8_DIR")
            else Path("/__missing_pythia__"),
            Path("/opt/hep/mg5/HEPTools/pythia8"),
        ]
    )
    delphes = _first_existing(
        [
            Path(os.environ["FINDINGZ_DELPHES_DIR"])
            if os.environ.get("FINDINGZ_DELPHES_DIR")
            else Path("/__missing_delphes__"),
            Path("/opt/hep/mg5/Delphes"),
        ]
    )
    delphes_card = _first_existing(
        [
            Path(os.environ["FINDINGZ_DELPHES_CARD"])
            if os.environ.get("FINDINGZ_DELPHES_CARD")
            else Path("/__missing_delphes_card__"),
            Path("/opt/hep/mg5/Template/Common/Cards/delphes_card_default.dat"),
        ]
    )
    missing = [
        name
        for name, value in [
            ("MadGraph", mg5),
            ("Pythia8", pythia),
            ("Delphes", delphes),
        ]
        if value is None
    ]
    return HepToolchainReport(
        available=not missing,
        mg5_executable=mg5,
        pythia8_dir=pythia,
        delphes_dir=delphes,
        delphes_card=delphes_card,
        image_id=os.environ.get("FINDINGZ_HEP_IMAGE_ID", "unversioned-local-stack"),
        detail="HEP toolchain ready" if not missing else f"Missing: {', '.join(missing)}",
    )


def render_madgraph_process_card(config: HepSimulationConfig, process_dir: Path) -> str:
    built_in_lines = {
        "dy_ee": ["generate p p > e+ e- QED=2 QCD=0"],
        "dy_mumu": ["generate p p > mu+ mu- QED=2 QCD=0"],
        "dy_ll": [
            "generate p p > e+ e- QED=2 QCD=0",
            "add process p p > mu+ mu- QED=2 QCD=0",
        ],
        "ee_mumu": ["generate e+ e- > mu+ mu- QED=2 QCD=0"],
        "ee_zh_mumu": ["generate e+ e- > z h, z > mu+ mu-"],
        "ee_ww_mumu": ["generate e+ e- > w+ w-, w+ > mu+ vm, w- > mu- vm~"],
    }
    process_lines = config.process_lines or built_in_lines.get(config.process)
    if process_lines is None:
        raise ValueError(f"No MadGraph definition was supplied for process {config.process}")
    return "\n".join(
        [
            "set automatic_html_opening False",
            f"import model {config.model}",
            *process_lines,
            f"output {process_dir} -f",
            "quit",
            "",
        ]
    )


def render_madevent_commands(config: HepSimulationConfig, run_name: str) -> str:
    lpp = 1 if config.collider == "pp" else 0
    pipeline_switches = (
        ["shower=Pythia8", "detector=Delphes"]
        if config.run_mode == "full"
        else ["shower=OFF", "detector=OFF"]
    )
    return "\n".join(
        [
            # Serial compilation avoids GNU Make jobserver descriptor failures in
            # containerized and emulated teaching environments.
            "set run_mode 0",
            "set nb_core 1",
            f"generate_events {run_name}",
            *pipeline_switches,
            f"set nevents {config.events}",
            f"set iseed {config.seed}",
            f"set lpp1 {lpp}",
            f"set lpp2 {lpp}",
            f"set ebeam1 {config.beam_energy_gev:.8g}",
            f"set ebeam2 {config.beam_energy_gev:.8g}",
            f"set mmll {config.min_mass_gev:.8g}",
            f"set mmllmax {config.max_mass_gev:.8g}",
            "done",
            "",
        ]
    )


_STANDARD_OMITTED_BRANCHES = {
    "Particle",
    "Track",
    "Tower",
    "EFlowTrack",
    "EFlowPhoton",
    "EFlowNeutralHadron",
}


def render_delphes_card(base_card: str, profile: DetectorProfile) -> str:
    """Create a reproducible standard or advanced card from the pinned MG5 base card."""
    header = (
        "# Finding Z detector profile: "
        f"{profile}\n# Generated from the selected detector card; original content follows.\n"
    )
    if profile == "advanced":
        return header + base_card

    output: list[str] = []
    omitted = 0
    for line in base_card.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[:2] == ["add", "Branch"]:
            branch_name = fields[3]
            if branch_name in _STANDARD_OMITTED_BRANCHES:
                output.append(f"# FindingZ standard omits: {line.strip()}")
                omitted += 1
                continue
        output.append(line)
    if omitted == 0:
        raise RuntimeError("Selected Delphes card contains no recognized low-level branches")
    return header + "\n".join(output) + "\n"


def resolve_detector_card(config: HepSimulationConfig, toolchain: HepToolchainReport) -> Path:
    """Use an explicit card root, packaged custom card, or legacy Delphes card."""
    configured = os.environ.get("FINDINGZ_CARD_ROOT")
    # An explicit root is authoritative; never silently substitute a detector.
    roots = ([Path(configured).expanduser()] if configured else
             [Path(__file__).parent / "resources", toolchain.delphes_dir])
    for root in roots:
        if root is None:
            continue
        root = root.resolve()
        selected = (root / config.detector_card).resolve()
        if not selected.is_relative_to(root):
            raise RuntimeError("Detector card escapes its configured root")
        if selected.is_file():
            return selected
    raise RuntimeError(f"Detector card not found in configured card roots: {config.detector_card}")


_CROSS_SECTION_PATTERN = re.compile(r"Cross-section\s*:\s*([0-9.eE+-]+)\s*\+-\s*([0-9.eE+-]+)\s*pb")


def extract_cross_section(log_path: Path) -> tuple[float, float]:
    """Read MadGraph's final total cross section and integration uncertainty."""
    matches = _CROSS_SECTION_PATTERN.findall(log_path.read_text(errors="replace"))
    if not matches:
        raise RuntimeError(f"MadGraph cross section was not found in {log_path}")
    value, uncertainty = matches[-1]
    return float(value), float(uncertainty)


def _pipeline_hash(config: HepSimulationConfig, image_id: str) -> str:
    payload = {
        "schema_version": 2,
        "config": config.model_dump(mode="json", exclude={"label"}),
        "image_id": image_id,
    }
    if config.run_mode == "full":
        configured = os.environ.get("FINDINGZ_CARD_ROOT")
        root = Path(configured).expanduser() if configured else Path(__file__).parent / "resources"
        card = (root / config.detector_card).resolve()
        if not card.is_relative_to(root.resolve()):
            raise RuntimeError("Detector card escapes its configured root")
        if card.is_file():
            payload["detector_card_sha256"] = hashlib.sha256(card.read_bytes()).hexdigest()
        elif configured:
            raise RuntimeError(f"Detector card not found: {card}")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:10]


def hep_run_directory(config: HepSimulationConfig, run_root: Path, image_id: str) -> Path:
    return Path(run_root) / f"{config.name}-{_pipeline_hash(config, image_id)}"


def _copy_checkpoint(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    shutil.copy2(source, temporary)
    if temporary.stat().st_size == 0:
        raise RuntimeError(f"Empty checkpoint produced: {source}")
    temporary.replace(destination)


def _find_output(root: Path, patterns: list[str], label: str) -> Path:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(root.rglob(pattern))
    nonempty = [path for path in matches if path.is_file() and path.stat().st_size > 0]
    if not nonempty:
        raise RuntimeError(f"MadGraph run did not produce a non-empty {label} output")
    return max(nonempty, key=lambda path: path.stat().st_mtime)


def _retain_diagnostics(run_dir: Path, manifest: dict[str, object]) -> None:
    """Keep text logs before deleting the process tree."""
    process_dir = run_dir / "process"
    for source in process_dir.rglob("*.log"):
        if source.is_symlink() or not source.is_file():
            continue
        if not source.resolve().is_relative_to(process_dir.resolve()):
            continue
        destination = run_dir / "logs" / "process" / source.relative_to(process_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    event_log = run_dir / "logs" / "event_generation.log"
    if event_log.exists():
        text = event_log.read_text(errors="replace")
        skipped = "can not run systematics since can not link python to lhapdf" in text.lower()
        manifest["systematics"] = {
            "status": "skipped" if skipped else "not_verified",
            "reason": "Python LHAPDF interface unavailable" if skipped else
                      "No systematics completion check is implemented",
            "source": "logs/event_generation.log",
        }
    manifest["diagnostic_logs"] = sorted(
        str(path.relative_to(run_dir)) for path in (run_dir / "logs").rglob("*.log")
        if path.is_file()
    )


def _apply_standard_retention(run_dir: Path, manifest: dict[str, object]) -> None:
    """Validate retained checkpoints, then remove reproducible transient artifacts."""
    stages = manifest.get("stages")
    if not isinstance(stages, dict):
        raise TypeError("Cannot apply retention policy without a stage manifest")

    retained_stages = {
        str(name): str(relative_path)
        for name, relative_path in stages.items()
        if name != "shower"
    }
    resolved_run_dir = run_dir.resolve()
    for name, relative_path in retained_stages.items():
        checkpoint = (run_dir / relative_path).resolve()
        if not checkpoint.is_relative_to(resolved_run_dir):
            raise RuntimeError(f"Retained stage {name} points outside its run directory")
        if not checkpoint.is_file() or checkpoint.stat().st_size == 0:
            raise RuntimeError(f"Retained stage {name} is missing or empty: {checkpoint}")

    _retain_diagnostics(run_dir, manifest)
    retain_generator_details(run_dir)
    removed: list[str] = []
    for relative_path in (Path("shower"), Path("process")):
        transient = run_dir / relative_path
        if transient.is_dir():
            shutil.rmtree(transient)
            removed.append(str(relative_path))
        elif transient.exists():
            transient.unlink()
            removed.append(str(relative_path))

    manifest["stages"] = retained_stages
    manifest["retention"] = {
        "profile": "standard-v1",
        "kept": sorted(set(retained_stages.values())),
        "removed": removed,
        "policy": (
            "Keep LHE, one Delphes ROOT file, analysis CSVs, cards, logs, and manifest. "
            "Remove transient Pythia8 HepMC and the generated MadGraph process tree "
            "after retained checkpoints validate."
        ),
    }


def extract_lhe_truth(lhe_path: Path) -> pd.DataFrame:
    """Extract final-state ee/mumu pairs from an LHE checkpoint."""
    opener = gzip.open if lhe_path.suffix == ".gz" else Path.open
    rows: list[dict[str, object]] = []
    in_event = False
    event_lines: list[str] = []
    with opener(lhe_path, "rt") as source:
        for raw_line in source:
            line = raw_line.strip()
            if line == "<event>":
                in_event = True
                event_lines = []
            elif line == "</event>":
                if event_lines:
                    particles = _parse_lhe_event(event_lines)
                    row = _lhe_pair_row(len(rows), particles)
                    if row is not None:
                        rows.append(row)
                in_event = False
            elif in_event and line and not line.startswith("#"):
                event_lines.append(line)
    return pd.DataFrame(rows)


def _parse_lhe_event(lines: list[str]) -> list[dict[str, float | int]]:
    particles: list[dict[str, float | int]] = []
    for line in lines[1:]:  # first line is the event header
        fields = line.split()
        if len(fields) < 11:
            continue
        particles.append(
            {
                "pid": int(fields[0]),
                "status": int(fields[1]),
                "px": float(fields[6]),
                "py": float(fields[7]),
                "pz": float(fields[8]),
                "energy": float(fields[9]),
                "mass": float(fields[10]),
            }
        )
    return particles


def _lhe_pair_row(
    event_id: int, particles: list[dict[str, float | int]]
) -> dict[str, object] | None:
    final_leptons = [
        particle
        for particle in particles
        if particle["status"] == 1 and abs(int(particle["pid"])) in {11, 13}
    ]
    for abs_pid, channel, flavor in [(11, "ee", "e"), (13, "mumu", "mu")]:
        negative = next((p for p in final_leptons if int(p["pid"]) == abs_pid), None)
        positive = next((p for p in final_leptons if int(p["pid"]) == -abs_pid), None)
        if negative is None or positive is None:
            continue
        row: dict[str, object] = {
            "event_id": event_id,
            "channel": channel,
            "weight": 1.0,
            "source": "madgraph_lhe",
        }
        for index, (particle, charge) in enumerate([(negative, -1), (positive, 1)], 1):
            px, py, pz = (float(particle[key]) for key in ("px", "py", "pz"))
            pt = math.hypot(px, py)
            row.update(
                {
                    f"l{index}_pt": pt,
                    f"l{index}_eta": math.asinh(pz / max(pt, 1e-12)),
                    f"l{index}_phi": math.atan2(py, px),
                    f"l{index}_mass": float(particle["mass"]),
                    f"l{index}_charge": charge,
                    f"l{index}_flavor": flavor,
                }
            )
        return row
    return None


def extract_delphes_dileptons(root_path: Path) -> pd.DataFrame:
    """Convert pinned Delphes Electron/Muon branches into the FindingZ CSV schema."""
    try:
        import awkward as ak
        import uproot
    except ImportError as error:
        raise RuntimeError(
            "The full HEP backend requires the optional 'hep' dependencies: uproot and awkward"
        ) from error

    rows: list[dict[str, object]] = []
    with uproot.open(root_path) as root_file:
        tree = root_file["Delphes"]
        collections = {}
        for name in ("Electron", "Muon"):
            collections[name] = {
                field: ak.to_list(tree[f"{name}.{field}"].array(library="ak"))
                for field in ("PT", "Eta", "Phi", "Charge")
            }
        event_count = int(tree.num_entries)

    for event_id in range(event_count):
        candidates: list[tuple[float, str, list[tuple[float, float, float, int]]]] = []
        for name, channel, flavor in [("Electron", "ee", "e"), ("Muon", "mumu", "mu")]:
            values = collections[name]
            objects = list(
                zip(
                    values["PT"][event_id],
                    values["Eta"][event_id],
                    values["Phi"][event_id],
                    values["Charge"][event_id],
                )
            )
            pairs = [
                [first, second]
                for first_index, first in enumerate(objects)
                for second in objects[first_index + 1 :]
                if int(first[3]) + int(second[3]) == 0
            ]
            if pairs:
                best = max(pairs, key=lambda pair: float(pair[0][0]) + float(pair[1][0]))
                candidates.append((sum(float(item[0]) for item in best), channel, best))
        if not candidates:
            continue
        _, channel, pair = max(candidates, key=lambda item: item[0])
        flavor = "e" if channel == "ee" else "mu"
        lepton_mass = 0.000511 if flavor == "e" else 0.10566
        pair = sorted(pair, key=lambda item: int(item[3]))
        row: dict[str, object] = {
            "event_id": event_id,
            "channel": channel,
            "weight": 1.0,
            "source": "madgraph_pythia8_delphes",
            "accepted": True,
        }
        for index, item in enumerate(pair, 1):
            pt, eta, phi, charge = item
            row.update(
                {
                    f"l{index}_pt": float(pt),
                    f"l{index}_eta": float(eta),
                    f"l{index}_phi": float(phi),
                    f"l{index}_mass": lepton_mass,
                    f"l{index}_charge": int(charge),
                    f"l{index}_flavor": flavor,
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def run_hep_simulation(
    config: HepSimulationConfig,
    run_root: Path | str = "runs",
    *,
    toolchain: HepToolchainReport | None = None,
    runner: CommandRunner | None = None,
    timeout_s: int = 1_800,
    progress: ProgressCallback | None = None,
) -> SimulationRun:
    """Run a bounded MadGraph job, optionally followed by Pythia8 and Delphes."""
    notify = progress or (lambda _message, _fraction: None)
    notify("Checking the generator toolchain", 0.02)
    toolchain = toolchain or probe_hep_toolchain()
    if toolchain.mg5_executable is None:
        raise RuntimeError(
            f"MadGraph is unavailable ({toolchain.detail}). "
            "Launch FindingZ inside the course HEP container."
        )
    if config.run_mode == "full" and not toolchain.available:
        raise RuntimeError(
            f"Full HEP toolchain is unavailable ({toolchain.detail}). "
            "Launch FindingZ inside the course HEP container."
        )
    runner = runner or SubprocessRunner()
    run_dir = hep_run_directory(config, Path(run_root), toolchain.image_id)
    run_id = run_dir.name
    truth_path = run_dir / "truth.csv"
    detector_path = (
        run_dir / "detector" / "detector.csv"
        if config.run_mode == "full"
        else run_dir / "truth.csv"
    )
    analysis_path = run_dir / "analysis.csv"
    manifest_path = run_dir / "manifest.json"
    expected = [truth_path, analysis_path, manifest_path]
    if config.run_mode == "full":
        expected.append(detector_path)
    if all(path.exists() for path in expected):
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("status") == "complete":
            notify("Found a matching completed checkpoint", 0.95)
            if config.label:
                manifest["label"] = config.label
            _apply_standard_retention(run_dir, manifest)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            notify("Checkpoint ready", 1.0)
            return SimulationRun(
                run_dir, truth_path, detector_path, analysis_path, manifest_path, reused=True
            )

    cards_dir = run_dir / "cards"
    logs_dir = run_dir / "logs"
    process_dir = run_dir / "process"
    cards_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "schema_version": 2,
        "run_id": run_id,
        "label": config.label or run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "pipeline": (
            "MadGraph5_aMC -> Pythia8 -> Delphes/FastJet -> FindingZ"
            if config.run_mode == "full"
            else "MadGraph5_aMC (parton level) -> FindingZ"
        ),
        "image_id": toolchain.image_id,
        "config": config.model_dump(mode="json", exclude={"label"}),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    try:
        notify("Building the MadGraph process", 0.10)
        process_card = cards_dir / "madgraph_process.mg5"
        process_card.write_text(render_madgraph_process_card(config, process_dir))
        runner.run(
            [str(toolchain.mg5_executable), str(process_card)],
            cwd=run_dir,
            log_path=logs_dir / "madgraph_process.log",
            timeout_s=timeout_s,
        )
        notify("Process code generated; preparing the event run", 0.25)
        detector_card_path: Path | None = None
        if config.run_mode == "full":
            notify("Preparing the collider detector card", 0.30)
            base_detector_card = resolve_detector_card(config, toolchain)
            detector_card = render_delphes_card(
                base_detector_card.read_text(), config.output_detail
            )
            detector_card_path = cards_dir / "delphes_card.dat"
            detector_card_path.write_text(detector_card)
            (process_dir / "Cards" / "delphes_card.dat").write_text(detector_card)
        madevent_card = cards_dir / "madevent_commands.txt"
        madevent_card.write_text(render_madevent_commands(config, "run_01"))
        long_stage = (
            "MadGraph → Pythia8 → Delphes running; see live output below"
            if config.run_mode == "full"
            else "MadGraph compilation, integration and event generation; see live output below"
        )
        notify(long_stage, 0.35)
        runner.run(
            [str(process_dir / "bin" / "madevent"), str(madevent_card)],
            cwd=process_dir,
            log_path=logs_dir / "event_generation.log",
            timeout_s=timeout_s,
        )
        notify("Generator stages finished; collecting checkpoints", 0.72)

        lhe_source = _find_output(process_dir / "Events", ["*.lhe", "*.lhe.gz"], "LHE")
        lhe_path = (
            run_dir
            / "matrix_element"
            / ("events.lhe.gz" if lhe_source.suffix == ".gz" else "events.lhe")
        )
        _copy_checkpoint(lhe_source, lhe_path)

        notify("Extracting parton-level dilepton objects", 0.78)
        truth = extract_lhe_truth(lhe_path)
        if truth.empty:
            raise RuntimeError("No final-state ee or mumu pair was found in the LHE output")
        truth.to_csv(truth_path, index=False)
        event_log = logs_dir / "event_generation.log"
        cross_section_pb, cross_section_uncertainty_pb = extract_cross_section(event_log)

        stages: dict[str, str] = {
            "matrix_element": str(lhe_path.relative_to(run_dir)),
            "analysis_input": str(truth_path.relative_to(run_dir)),
        }
        if detector_card_path is not None:
            stages["detector_card"] = str(detector_card_path.relative_to(run_dir))
        analysis_input = truth
        if config.run_mode == "full":
            notify("Validating Pythia8 and Delphes outputs", 0.84)
            _find_output(
                process_dir / "Events",
                ["*pythia8_events.hepmc", "*pythia8_events.hepmc.gz"],
                "HepMC",
            )
            root_source = _find_output(
                process_dir / "Events", ["*delphes_events.root", "*.root"], "Delphes ROOT"
            )
            root_path = run_dir / "detector" / "delphes.root"
            _copy_checkpoint(root_source, root_path)
            notify("Extracting reconstructed Delphes objects", 0.89)
            detector = extract_delphes_dileptons(root_path)
            if detector.empty:
                raise RuntimeError("No opposite-sign ee or mumu pair was found in Delphes output")
            detector.to_csv(detector_path, index=False)
            analysis_input = detector
            stages.update(
                {
                    "detector_root": str(root_path.relative_to(run_dir)),
                    "detector_csv": str(detector_path.relative_to(run_dir)),
                    "analysis_input": str(detector_path.relative_to(run_dir)),
                }
            )

        notify("Computing analysis observables", 0.94)
        analysis = add_observables(analysis_input)
        analysis.to_csv(analysis_path, index=False)
        stages["analysis"] = str(analysis_path.relative_to(run_dir))
        manifest.update(
            {
                "status": "finalizing",
                "generated_events": config.events,
                "truth_dileptons": len(truth),
                "accepted_dileptons": len(analysis),
                "cross_section_pb": cross_section_pb,
                "cross_section_uncertainty_pb": cross_section_uncertainty_pb,
                "stages": stages,
                "provenance": (
                    "Leading-order matrix elements from MadGraph5_aMC."
                    if config.run_mode == "madgraph"
                    else "Leading-order matrix elements from MadGraph5_aMC, Pythia8 "
                    "shower/hadronization, and Delphes detector simulation using its "
                    "FastJet modules."
                ),
            }
        )
        notify("Applying the storage and provenance policy", 0.98)
        _apply_standard_retention(run_dir, manifest)
        manifest["status"] = "complete"
    except Exception as error:
        notify(f"Run failed: {error}", 1.0)
        manifest.update({"status": "failed", "error": str(error)})
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        raise
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    notify("Simulation complete", 1.0)
    return SimulationRun(
        run_dir, truth_path, detector_path, analysis_path, manifest_path, reused=False
    )
