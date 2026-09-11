from __future__ import annotations

import argparse
from pathlib import Path

from findingz.hep_pipeline import (
    HepSimulationConfig,
    probe_hep_toolchain,
    run_hep_simulation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the full FindingZ HEP stack")
    parser.add_argument("--events", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("runs"))
    args = parser.parse_args()

    report = probe_hep_toolchain()
    if not report.available:
        raise SystemExit(f"HEP toolchain unavailable: {report.detail}")
    config = HepSimulationConfig(events=args.events, process="dy_mumu", seed=225)
    run = run_hep_simulation(config, args.output)
    if run.analysis_path.stat().st_size == 0:
        raise SystemExit("Full pipeline produced an empty analysis checkpoint")
    print(f"HEP pipeline smoke test passed: {run.run_dir}")


if __name__ == "__main__":
    main()
