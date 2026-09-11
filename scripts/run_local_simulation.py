from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from findingz.simulation import ToySimulationConfig, run_toy_simulation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the FindingZ local toy simulation")
    parser.add_argument("--events", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=225)
    parser.add_argument("--z-mass", type=float, default=91.1876)
    parser.add_argument("--z-width", type=float, default=2.4952)
    parser.add_argument("--continuum-fraction", type=float, default=0.30)
    parser.add_argument("--detector-resolution", type=float, default=0.02)
    parser.add_argument("--output", type=Path, default=Path("runs"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ToySimulationConfig(
        events=args.events,
        seed=args.seed,
        z_mass_gev=args.z_mass,
        z_width_gev=args.z_width,
        continuum_fraction=args.continuum_fraction,
        detector_pt_resolution=args.detector_resolution,
    )
    run = run_toy_simulation(config, args.output)
    manifest = json.loads(run.manifest_path.read_text())
    action = "Reused" if run.reused else "Created"
    print(f"{action} {run.run_dir}")
    print(
        f"Generated {manifest['generated_events']} events; "
        f"accepted {manifest['accepted_events']}"
    )


if __name__ == "__main__":
    main()
