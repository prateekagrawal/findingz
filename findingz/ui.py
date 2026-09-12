from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from queue import Empty, SimpleQueue
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
from matplotlib.figure import Figure

from findingz.analysis_variables import (
    AnalysisVariable,
    apply_windows,
    load_variable_catalog,
    slider_bounds,
    variable_catalog_path,
)
from findingz.catalog import catalog_path, load_catalog
from findingz.counting import summarize_cut_and_count, weighted_yield
from findingz.event_display import render_event_inspector
from findingz.generator_details import render_generator_details, render_run_files
from findingz.hep_pipeline import (
    MAX_HEP_EVENTS,
    HepSimulationConfig,
    hep_run_directory,
    probe_hep_toolchain,
    run_hep_simulation,
)
from findingz.hypotheses import (
    AnalysisSample,
    build_sample_library,
    compatible_counting_backgrounds,
    validate_counting_samples,
)
from findingz.run_choices import fresh_config, matching_run, rename_saved_run
from findingz.run_progress import render_progress_details
from findingz.runs import list_saved_runs
from findingz.simulation import (
    SimulationRun,
    ToySimulationConfig,
    run_toy_simulation,
)

logger = logging.getLogger("findingz.app")


def _run_root() -> Path:
    configured = os.environ.get("FINDINGZ_RUN_ROOT")
    return Path(configured).expanduser().resolve() if configured else Path.cwd() / "runs"


@st.cache_resource
def _simulation_executor() -> ThreadPoolExecutor:
    """One worker keeps a student container responsive without oversubscribing it."""
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="findingz-simulation")


def _background_simulation(
    config: ToySimulationConfig | HepSimulationConfig,
    toolchain: Any,
    updates: SimpleQueue[tuple[str, float]],
) -> SimulationRun:
    def report(message: str, fraction: float) -> None:
        updates.put((message, fraction))

    if isinstance(config, ToySimulationConfig):
        report("Generating the instructor toy sample", 0.25)
        result = run_toy_simulation(config, _run_root())
        report("Toy checkpoint ready", 1.0)
        return result
    return run_hep_simulation(
        config,
        _run_root(),
        toolchain=toolchain,
        progress=report,
    )


def _saved_run_payload(run: SimulationRun, run_depth: str) -> dict[str, object]:
    return {
        "run_dir": str(run.run_dir),
        "truth_path": str(run.truth_path),
        "detector_path": str(run.detector_path),
        "analysis_path": str(run.analysis_path),
        "manifest_path": str(run.manifest_path),
        "reused": run.reused,
        "run_depth": run_depth,
    }


def _queue_simulation(config, toolchain, run_depth):
    st.session_state.pop("simulation_run", None)
    updates: SimpleQueue[tuple[str, float]] = SimpleQueue()
    future = _simulation_executor().submit(_background_simulation, config, toolchain, updates)
    st.session_state["simulation_job"] = {
        "future": future, "updates": updates, "message": "Simulation queued", "fraction": 0.0,
        "run_depth": run_depth, "started_at": time.monotonic(), "stage_started_at": time.monotonic(),
        "summary": f"{config.events:,} events · seed {config.seed} · {run_depth}",
        "run_dir": str(hep_run_directory(config, _run_root(), toolchain.image_id))
                   if isinstance(config, HepSimulationConfig) else None,
    }


def _render_duplicate_choice():
    pending = st.session_state.get("duplicate_run")
    if not pending:
        return
    existing = pending["existing"]
    with st.container(border=True):
        st.subheader("These settings already have a saved sample")
        st.write(f"**{existing.label}** (`{existing.run_id}`)")
        st.caption(f"Submitted settings: {pending['config'].events:,} events · "
                   f"seed {pending['config'].seed}. No simulation has started.")
        action = st.radio("What would you like to do?", ["Load existing run", "Rename existing run",
                          "Generate fresh sample"], key="duplicate_action")
        label = pending["config"].label or existing.label
        if action == "Rename existing run":
            label = st.text_input("New display name", value=label, max_chars=80,
                                  key="duplicate_label")
            st.caption("Changes only the display name; events and run ID stay unchanged.")
        elif action == "Generate fresh sample":
            st.caption(f"Uses a new random seed ({pending['fresh'].seed}) to generate an independent "
                       "sample. All other submitted settings stay the same; the old run is kept.")
        accept, cancel = st.columns(2)
        if cancel.button("Cancel", key="duplicate_cancel"):
            st.session_state.pop("duplicate_run", None)
            st.rerun()
        if accept.button("Continue", key="duplicate_continue", type="primary",
                         disabled=action == "Rename existing run" and not label.strip()):
            if action == "Generate fresh sample":
                _queue_simulation(pending["fresh"], pending["toolchain"], pending["depth"])
            else:
                if not existing.manifest_path.is_file():
                    st.error("This saved run is no longer available. Cancel and submit again.")
                    return
                if action == "Rename existing run":
                    rename_saved_run(existing.manifest_path, label)
                directory = existing.manifest_path.parent
                run = SimulationRun(directory, directory / "truth.csv", directory / "detector.csv",
                                    existing.analysis_path, existing.manifest_path, reused=True)
                st.session_state["simulation_run"] = _saved_run_payload(run, pending["depth"])
            st.session_state.pop("duplicate_run", None)
            st.rerun()


@st.fragment(run_every=1.0)
def _render_simulation_job() -> None:
    job = st.session_state.get("simulation_job")
    if not isinstance(job, dict):
        return
    updates = job["updates"]
    try:
        while True:
            message, fraction = updates.get_nowait()
            if message != job.get("message"):
                job["stage_started_at"] = time.monotonic()
            job["message"] = message
            job["fraction"] = fraction
    except Empty:
        pass

    future: Future[SimulationRun] = job["future"]
    if future.done():
        try:
            run = future.result()
            st.session_state["simulation_run"] = _saved_run_payload(run, job["run_depth"])
        except Exception as error:
            logger.exception("Background simulation failed")
            st.session_state["simulation_job_error"] = str(error)
        st.session_state.pop("simulation_job", None)
        st.rerun()

    message = str(job.get("message", "Waiting for the simulation worker"))
    with st.status(message, expanded=True):
        render_progress_details(job)


def _render_local_simulator() -> None:
    catalog = load_catalog()
    st.header("Event simulation")
    st.caption(
        "Choose a collider, physics model, hard process, and simulation level. "
        "This page reports generator outputs; distributions and selections live on Analysis."
    )

    toolchain = probe_hep_toolchain()
    mode = st.radio("Simulation view", ["New run", "Saved runs"], horizontal=True,
                    key="simulation_view", label_visibility="collapsed")
    if mode == "Saved runs":
        available_runs = {run.run_id: run for run in list_saved_runs(_run_root())}
        if not available_runs:
            st.info("No saved runs yet.")
            _render_simulation_job()
            return
        selected_run = st.selectbox(
            "Open saved run",
            list(available_runs),
            index=None,
            placeholder="Choose a previous run…",
            format_func=lambda run_id: available_runs[run_id].menu_label,
            key="simulation_saved_run",
        )
        _render_simulation_job()
        if selected_run is not None:
            selected = available_runs[selected_run]
            directory = selected.manifest_path.parent
            run = SimulationRun(
                directory,
                directory / "truth.csv",
                directory / "detector.csv",
                selected.analysis_path,
                selected.manifest_path,
                reused=True,
            )
            payload = _saved_run_payload(run, selected.run_type)
            payload["recalled"] = True
            st.session_state["simulation_run"] = payload
            _render_simulation_results()
        return
    job_active = isinstance(st.session_state.get("simulation_job"), dict)
    job_error = st.session_state.pop("simulation_job_error", None)
    if job_error:
        st.error(f"Simulation failed: {job_error}")
    run_types: list[str] = []
    if catalog.features.toy_generator:
        run_types.append("Toy Z test generator (instructor fallback)")
    if catalog.features.madgraph_only:
        run_types.append("MadGraph only (parton level)")
    if catalog.features.full_pipeline:
        run_types.append("Full pipeline (MadGraph + Pythia8 + Delphes/FastJet)")
    if not run_types:
        st.error("No simulation modes are currently released in the course catalogue.")
        return

    top_left, top_right = st.columns([1, 1])
    with top_left:
        run_depth = st.selectbox(
            "Run type",
            run_types,
            help=(
                "MadGraph-only is the regular matrix-element run. The full pipeline also "
                "showers the event and applies a fast detector simulation."
            ),
        )
    with top_right:
        run_label_input = st.text_input(
            "Run name (optional)",
            max_chars=80,
            placeholder="e.g. narrow Z window, seed 225",
            help=(
                "A persistent display name for the saved run. The immutable hashed run ID "
                "still records the physics configuration."
            ),
        )
    run_label = run_label_input.strip() or None
    is_toy = run_depth == "Toy Z test generator (instructor fallback)"
    is_full = run_depth.startswith("Full pipeline")

    if is_toy:
        st.warning(
            "Instructor smoke-test/fallback for one predefined Z-like process. It is "
            "not MadGraph, Pythia, Delphes, collider data, or a precision prediction."
        )
        with st.expander("Toy-generator settings", expanded=False):
            settings = st.columns(3)
            with settings[0]:
                events = st.slider("Generated events", 100, 10_000, 2_000, 100, key="toy_events")
                seed = st.number_input(
                    "Random seed", min_value=0, max_value=2**32 - 1, value=225, key="toy_seed"
                )
            with settings[1]:
                channels = st.multiselect(
                    "Dilepton channels",
                    ["ee", "mumu"],
                    default=["ee", "mumu"],
                    key="toy_channels",
                )
                continuum = st.slider("Continuum fraction", 0.0, 0.8, 0.30, 0.01)
            with settings[2]:
                z_mass = st.slider("Input resonance mass [GeV]", 85.0, 97.0, 91.1876, 0.01)
                z_width = st.slider("Input resonance width [GeV]", 0.5, 6.0, 2.4952, 0.01)
                resolution = st.slider("Lepton pT resolution", 0.0, 0.10, 0.02, 0.002)
        run_button = st.button(
            "Simulation running…" if job_active else "Run toy test",
            type="primary",
            disabled=job_active,
            width="stretch",
        )
    else:
        colliders = catalog.available_colliders(full_pipeline=is_full)
        if not colliders:
            st.error("No compatible colliders are currently released.")
            return
        selection_columns = st.columns([1, 1, 1.8])
        with selection_columns[0]:
            collider_id = st.selectbox(
                "Collider",
                list(colliders),
                format_func=lambda item: colliders[item].label,
            )
        collider_entry = colliders[collider_id]
        center_of_mass_energy = 2.0 * collider_entry.beam_energy_gev
        energy_label = (
            f"{center_of_mass_energy / 1_000:g} TeV"
            if center_of_mass_energy >= 1_000
            else f"{center_of_mass_energy:g} GeV"
        )
        detector_id = "none"
        detector_card = "none"
        detector_description = "Parton level; no detector simulation"
        output_detail = "standard"
        if is_full:
            available_detectors = catalog.available_detectors()
            detector_id = collider_entry.default_detector_id or ""
            if detector_id not in available_detectors:
                st.error("This collider has no released default detector model.")
                return
            detector_entry = available_detectors[detector_id]
            detector_card = detector_entry.card
            detector_description = detector_entry.label

        released_models = catalog.available_models()
        models = {
            model_id: entry
            for model_id, entry in released_models.items()
            if catalog.available_processes(collider_id, model_id, full_pipeline=is_full)
        }
        if not models:
            st.error("No compatible physics models are currently released.")
            return
        with selection_columns[1]:
            model_id = st.selectbox(
                "Physics model",
                list(models),
                format_func=lambda item: models[item].label,
            )
        model_entry = models[model_id]
        processes = catalog.available_processes(collider_id, model_id, full_pipeline=is_full)
        with selection_columns[2]:
            process_id = st.selectbox(
                "Hard process",
                list(processes),
                format_func=lambda item: processes[item].label,
            )
        process_entry = processes[process_id]
        st.caption(
            f"{collider_entry.label}: {collider_entry.beam_type} beams at √s = "
            f"{energy_label} · {detector_description}"
        )

        backend_ready = toolchain.available if is_full else toolchain.mg5_executable is not None
        readiness = (
            "Simulation running — you can switch to Analysis"
            if job_active
            else ("Generator ready" if backend_ready else toolchain.detail)
        )
        st.caption(readiness)
        with st.expander("Generation settings", expanded=False):
            settings = st.columns(3)
            with settings[0]:
                events = st.slider(
                    "Generated events", 100, MAX_HEP_EVENTS, 1_000, 100, key="hep_events"
                )
            with settings[1]:
                seed = st.number_input(
                    "Random seed",
                    min_value=1,
                    max_value=900_000_000,
                    value=225,
                    key="hep_seed",
                )
            with settings[2]:
                override_energy = st.checkbox(
                    "Override collider energy",
                    value=False,
                    key=f"override_energy_{collider_id}",
                    help="Leave off to use the named collider preset.",
                )
                beam_energy = collider_entry.beam_energy_gev
                if override_energy:
                    beam_energy = st.number_input(
                        "Energy per beam [GeV] (override)",
                        min_value=10.0,
                        max_value=50_000.0,
                        value=collider_entry.beam_energy_gev,
                        step=0.1 if collider_entry.beam_type == "ee" else 500.0,
                        key=f"beam_energy_{collider_id}",
                    )
            if is_full:
                detail_label = st.selectbox(
                    "Saved detector output detail",
                    [
                        "Compact reconstructed objects (recommended)",
                        "Full Delphes object record (advanced, larger file)",
                    ],
                    help=(
                        "Compact keeps reconstructed leptons, photons, jets and missing "
                        "energy. Full also keeps generator particles, tracks, calorimeter "
                        "towers and particle-flow collections."
                    ),
                )
                output_detail = "advanced" if detail_label.startswith("Full") else "standard"
            min_mass, max_mass = st.slider(
                "Generated dilepton mass range [GeV]",
                10.0,
                1_000.0,
                collider_entry.mass_window_gev,
                5.0,
                help="Both bounds are passed to the MadGraph run card.",
                key=f"mass_window_{collider_id}",
            )
        if not backend_ready:
            st.info(
                f"{toolchain.detail}. Start the app with `docker compose -f "
                "docker-compose.hep.yml up` to enable this backend."
            )
        run_button = st.button(
            (
                "Simulation running…"
                if job_active
                else ("Run full HEP pipeline" if is_full else "Run MadGraph")
            ),
            type="primary",
            disabled=job_active or not backend_ready,
            width="stretch",
        )

    if run_button:
        if is_toy:
            submitted_config: ToySimulationConfig | HepSimulationConfig = ToySimulationConfig(
                label=run_label,
                events=events,
                seed=int(seed),
                channels=channels,
                z_mass_gev=z_mass,
                z_width_gev=z_width,
                continuum_fraction=continuum,
                detector_pt_resolution=resolution,
            )
        else:
            submitted_config = HepSimulationConfig(
                label=run_label,
                events=events,
                seed=int(seed),
                process=process_id,
                process_lines=process_entry.madgraph_lines,
                collider_id=collider_id,
                collider=collider_entry.beam_type,
                model=model_entry.madgraph_name,
                run_mode="full" if is_full else "madgraph",
                beam_energy_gev=beam_energy,
                min_mass_gev=min_mass,
                max_mass_gev=max_mass,
                detector_id=detector_id,
                detector_card=detector_card,
                output_detail=output_detail,
            )
        existing = matching_run(submitted_config, _run_root(), toolchain.image_id)
        st.session_state.pop("duplicate_run", None)
        if existing:
            st.session_state.pop("duplicate_action", None)
            st.session_state.pop("duplicate_label", None)
            st.session_state["duplicate_run"] = {
                "existing": existing, "config": submitted_config, "toolchain": toolchain,
                "depth": run_depth,
                "fresh": fresh_config(submitted_config, _run_root(), toolchain.image_id),
            }
        else:
            _queue_simulation(submitted_config, toolchain, run_depth)
        st.rerun()

    _render_duplicate_choice()
    _render_simulation_job()
    saved = st.session_state.get("simulation_run", {})
    if not isinstance(saved, dict) or not saved.get("recalled"):
        _render_simulation_results()


def _render_simulation_results() -> None:
    if "simulation_run" in st.session_state:
        saved = st.session_state["simulation_run"]
        if isinstance(saved, str):  # migrate sessions created by the first local prototype
            legacy_dir = Path(saved)
            saved = {
                "run_dir": saved,
                "truth_path": str(legacy_dir / "truth.csv"),
                "detector_path": str(legacy_dir / "detector.csv"),
                "analysis_path": str(legacy_dir / "analysis.csv"),
                "manifest_path": str(legacy_dir / "manifest.json"),
                "reused": bool(st.session_state.get("simulation_reused")),
            }
        run = SimulationRun(
            run_dir=Path(saved["run_dir"]),
            truth_path=Path(saved["truth_path"]),
            detector_path=Path(saved["detector_path"]),
            analysis_path=Path(saved["analysis_path"]),
            manifest_path=Path(saved["manifest_path"]),
            reused=bool(saved["reused"]),
        )
        manifest = json.loads(run.manifest_path.read_text())
        st.subheader(f"Run results — {manifest.get('label') or manifest['run_id']}")
        config = manifest.get("config", {})
        st.caption(" · ".join(str(config[key]) for key in
                             ("collider_id", "model", "process", "run_mode") if config.get(key)))
        action = "Opened saved run" if saved.get("recalled") else (
            "Reused checkpoint" if run.reused else "Created new run")
        st.success(f"{action}: **{manifest.get('label', manifest['run_id'])}** "
                   f"(`{manifest['run_id']}`)")
        metric_columns = st.columns(3)
        metric_columns[0].metric("Generated events", manifest["generated_events"])
        accepted = manifest.get("accepted_events", manifest.get("accepted_dileptons"))
        metric_columns[1].metric("Available dilepton events", accepted)
        cross_section = manifest.get("cross_section_pb")
        uncertainty = manifest.get("cross_section_uncertainty_pb")
        if cross_section is None:
            metric_columns[2].metric("Total cross section", "Not defined for toy run")
        else:
            metric_columns[2].metric(
                "MadGraph total cross section",
                f"{cross_section:.6g} pb",
                delta=f"± {uncertainty:.3g} pb integration" if uncertainty is not None else None,
                delta_color="off",
            )
        matrix_element = manifest.get("stages", {}).get("matrix_element")
        if matrix_element:
            st.caption("Cross section includes generator cuts; ± denotes integration uncertainty.")
            render_generator_details(run.run_dir)
        render_event_inspector(run.run_dir, manifest)
        render_run_files(run.run_dir, manifest, run.analysis_path)


def _render_jupyter_entrypoint() -> None:
    notebook_path = "notebooks/06_sample_analysis.ipynb"
    jupyter_url = os.environ.get("FINDINGZ_JUPYTER_URL", "").strip()
    st.caption(
        "Prefer Python? Explore object definitions and custom analyses in the starter notebook."
    )
    if jupyter_url:
        st.link_button("Open Jupyter analysis", jupyter_url)
    else:
        st.caption(
            f"Open the starter notebook, {notebook_path}, in JupyterLab "
            "from your course-materials folder."
        )
    with st.expander("Using the analysis notebook"):
        st.markdown(
            "1. Open the notebook and run the cells from the top.\n"
            "2. Choose sample IDs from the table it creates.\n"
            "3. Edit the highlighted cuts or electron-definition values and rerun the cells.\n"
            "4. Save or rename the notebook normally; your copy and outputs persist between "
            "sessions.\n\n"
            "Use your course's Python kernel if Jupyter asks you to choose one "
            "(**Python (Finding Z)** in the local setup)."
        )


def _sample_config_summary(sample: AnalysisSample) -> str:
    if sample.kind == "prepared":
        return "Synthetic sample · no physical cross-section normalization"
    config = sample.config
    mode = "Full pipeline" if config.get("run_mode") == "full" else "MadGraph only"
    energy = config.get("beam_energy_gev")
    energy_text = f" · {2 * float(energy):g} GeV √s" if isinstance(energy, int | float) else ""
    cross_section = (
        f"{sample.cross_section_pb:.5g} pb"
        if sample.cross_section_pb is not None
        else "no cross section"
    )
    return (
        f"{mode} · {config.get('collider_id', config.get('collider', 'unknown collider'))}"
        f"{energy_text} · {config.get('model', 'unknown model')} · "
        f"{config.get('process', 'unknown process')} · {sample.generated_events or '?'} events "
        f"· {cross_section}"
    )


def _render_sample_details(
    samples: list[AnalysisSample], title: str = "Selected sample configurations"
) -> None:
    with st.expander(title, expanded=False):
        for sample in samples:
            st.markdown(f"**{sample.label}** (`{sample.sample_id}`)")
            st.caption(_sample_config_summary(sample))
            st.caption(sample.provenance)
            if sample.kind == "generated":
                st.json(sample.config, expanded=False)


def _analysis_frames(
    samples: list[AnalysisSample],
    *,
    luminosity_fb: float,
    expected_yields: bool,
    channels: list[str],
    windows: dict[str, tuple[float, float]],
    variables: dict[str, AnalysisVariable],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for sample in samples:
        frame = sample.expected_frame(luminosity_fb) if expected_yields else sample.load()
        if "channel" in frame:
            frame = frame.loc[frame["channel"].isin(channels)]
        frames[sample.sample_id] = apply_windows(frame, windows, variables)
    return frames


def _observable_bins(frames: list[pd.DataFrame], observable: str) -> np.ndarray:
    series = [frame[observable] for frame in frames if observable in frame and not frame.empty]
    if not series:
        return np.linspace(0.0, 1.0, 41)
    values = pd.concat(series, ignore_index=True)
    finite = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return np.linspace(0.0, 1.0, 41)
    lower, upper = float(finite.min()), float(finite.max())
    if lower == upper:
        padding = max(abs(lower) * 0.05, 0.5)
        lower, upper = lower - padding, upper + padding
    return np.linspace(lower, upper, 41)


def _render_variable_sliders(
    variables: dict[str, AnalysisVariable],
    frames: list[pd.DataFrame],
    *,
    prefix: str,
    defaults: dict[str, tuple[float, float]] | None = None,
    revision: str = "",
) -> dict[str, tuple[float, float]]:
    selection_signature = sha256(
        json.dumps(
            [
                {name: variable.model_dump() for name, variable in variables.items()},
                defaults,
                revision,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()[:12]
    selected = st.multiselect(
        "Cut on",
        list(variables),
        default=list(defaults or {}),
        format_func=lambda name: variables[name].label,
        help="Choose variables to show their cut sliders. Removing a variable removes its cut.",
        key=f"{prefix}_variables_{selection_signature}",
    )
    windows = {}
    for name in selected:
        variable = variables[name]
        lower, upper = slider_bounds(frames, variable)
        value = (defaults or {}).get(name, (lower, upper))
        # A copied cut must stay exact even when it extends beyond this sample's range.
        lower, upper = min(lower, value[0]), max(upper, value[1])
        signature = sha256(
            json.dumps(
                [variable.model_dump(), lower, upper, value, revision], sort_keys=True
            ).encode()
        ).hexdigest()[:12]
        windows[name] = st.slider(
            variable.label,
            lower,
            upper,
            value,
            variable.step,
            help=variable.description,
            key=f"{prefix}_{name}_{signature}",
        )
    return windows


def _render_dataset_plot(
    selected_samples: list[AnalysisSample],
    variables: dict[str, AnalysisVariable],
    source_frames: dict[str, pd.DataFrame],
) -> tuple[list[str], dict[str, tuple[float, float]]]:
    st.subheader("Plot distributions")
    st.caption(
        "Choose a variable to plot. Optionally select variables under ‘Cut on’ to add "
        "range sliders. The same cuts apply to every selected sample."
    )
    controls, display = st.columns([1, 2.2])
    with controls:
        channel_options = sorted(
            {
                str(channel)
                for frame in source_frames.values()
                if "channel" in frame
                for channel in frame["channel"].dropna().unique()
            }
        )
        channels = (
            st.multiselect(
                "Channels", channel_options, default=channel_options, key="analysis_channels"
            )
            if channel_options
            else []
        )
        observable = st.selectbox(
            "Observable",
            list(variables),
            format_func=lambda name: variables[name].label,
            key="analysis_observable",
        )
        windows = _render_variable_sliders(
            variables,
            list(source_frames.values()),
            prefix="plot_cut",
        )
        normalization = st.radio(
            "Plot normalization",
            ["Shape only (unit area)", "Expected yields"],
            help=(
                "Shape-only compares distributions. Expected yields uses the sample's "
                "cross section and the chosen luminosity."
            ),
        )
        generated = any(sample.kind == "generated" for sample in selected_samples)
        luminosity = (
            st.number_input(
                "Integrated luminosity [fb⁻¹]",
                min_value=0.001,
                max_value=100_000.0,
                value=1.0,
                key="plot_luminosity",
            )
            if generated and normalization == "Expected yields"
            else 1.0
        )

    try:
        expected_yields = normalization == "Expected yields"
        frames = _analysis_frames(
            selected_samples,
            luminosity_fb=float(luminosity),
            expected_yields=expected_yields,
            channels=channels,
            windows=windows,
            variables=variables,
        )
        column = variables[observable].column
        bins = _observable_bins(list(frames.values()), column)
        figure = Figure(figsize=(8, 5))
        axis = figure.subplots()
        summary_rows = []
        for sample in selected_samples:
            frame = frames[sample.sample_id]
            weights = pd.to_numeric(frame.get("weight", pd.Series(1.0, index=frame.index)))
            source_integral = float(weights.sum())
            if not expected_yields and source_integral > 0.0:
                weights = weights / source_integral
            axis.hist(
                frame[column],
                bins=bins,
                weights=weights,
                histtype="step",
                linewidth=2.2,
                label=sample.label,
            )
            summary_rows.append(
                {
                    "sample": sample.label,
                    "selected rows": len(frame),
                    "yield before shape normalization": source_integral,
                }
            )
        axis.set_xlabel(variables[observable].label)
        axis.set_ylabel("Expected events" if expected_yields else "Fraction of sample")
        axis.grid(alpha=0.2)
        axis.legend()
        figure.tight_layout()
        with display:
            st.pyplot(figure)
            st.dataframe(pd.DataFrame(summary_rows), hide_index=True, width="stretch")
    except Exception as error:
        logger.exception("Dataset plotting failed")
        with display:
            st.error(f"Cannot compare these samples: {error}")
    return channels, windows


def _render_limit_estimate(
    library: dict[str, AnalysisSample],
    *,
    plot_selection: tuple[list[str], dict[str, tuple[float, float]]] | None,
) -> None:
    st.divider()
    st.subheader("Cut-and-count limit estimate")
    st.caption(
        "Choose a signal from any available sample; background choices match its configuration. "
        "These choices are independent of the plot. "
        "Define cuts here, or copy the current plot cuts once and edit them independently."
    )
    role_samples = list(library.values())
    if len(role_samples) < 2:
        st.info("At least two available samples are needed to assign signal and background roles.")
        return

    role_ids = [sample.sample_id for sample in role_samples]
    role_by_id = {sample.sample_id: sample for sample in role_samples}
    role_columns = st.columns(2)
    with role_columns[0]:
        signal_id = st.selectbox(
            "1. Signal sample",
            role_ids,
            index=0,
            format_func=lambda item: role_by_id[item].menu_label,
            key="count_signal",
        )
    signal = role_by_id[signal_id]
    background_options = compatible_counting_backgrounds(signal, library)
    previous_backgrounds = st.session_state.get("count_backgrounds")
    removed_backgrounds = []
    if previous_backgrounds is not None:
        retained = [
            sample_id for sample_id in previous_backgrounds if sample_id in background_options
        ]
        removed_backgrounds = [
            sample_id for sample_id in previous_backgrounds if sample_id not in background_options
        ]
        if removed_backgrounds:
            st.session_state["count_backgrounds"] = retained
    with role_columns[1]:
        background_ids = st.multiselect(
            "2. Compatible background samples",
            background_options,
            default=None,
            format_func=lambda item: role_by_id[item].menu_label,
            key="count_backgrounds",
            disabled=not background_options,
            help=(
                "Matches the signal's collider, beam energy, simulation level, detector, "
                "output profile, and generated mass range, with cross-section normalization. "
                "Processes and physics models may differ."
            ),
        )
    if removed_backgrounds:
        names = ", ".join(
            library[item].label if item in library else item for item in removed_backgrounds
        )
        st.info(f"Cleared backgrounds that no longer match the signal: {names}.")
    if not background_options:
        try:
            validate_counting_samples([signal])
        except ValueError as error:
            st.warning(f"This signal is not ready for counting: {error}")
        else:
            st.info(
                "No compatible background samples are available. Choose another signal "
                "or generate a background with the same simulation configuration."
            )
        _render_sample_details([signal], "Counting sample configurations")
        return
    if not background_ids:
        st.info("Choose one or more compatible background samples in step 2 to continue.")
        return

    backgrounds = [role_by_id[sample_id] for sample_id in background_ids]
    selected_samples = [signal, *backgrounds]
    all_generated = all(sample.kind == "generated" for sample in selected_samples)
    compatibility_error = None
    try:
        validate_counting_samples(selected_samples)
    except ValueError as error:
        compatibility_error = str(error)
        st.warning(f"These samples cannot be counted together: {error}")
    _render_sample_details(selected_samples, "Counting sample configurations")
    try:
        source_frames = {sample.sample_id: sample.load() for sample in selected_samples}
        variables = load_variable_catalog().available(selected_samples, source_frames)
    except Exception as error:
        logger.exception("Loading counting samples failed")
        st.error(f"Cannot load counting variables or samples: {error}")
        return
    channel_options = sorted(
        {
            str(channel)
            for frame in source_frames.values()
            if "channel" in frame
            for channel in frame["channel"].dropna().unique()
        }
    )
    scope = sha256(
        json.dumps(
            [
                [sample.sample_id for sample in selected_samples],
                {name: value.model_dump() for name, value in variables.items()},
                channel_options,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()[:12]
    if st.session_state.get("count_selection_scope") != scope:
        st.session_state["count_selection_scope"] = scope
        st.session_state["count_copied_selection"] = None
        st.session_state["count_copy_revision"] = 0
    controls, display = st.columns([1, 2.2])
    with controls:
        if st.button("Copy cuts from plot", disabled=plot_selection is None):
            plot_channels, plot_windows = plot_selection
            missing = set(plot_windows) - set(variables)
            channel_missing = bool(plot_channels) and any(
                "channel" not in frame for frame in source_frames.values()
            )
            if missing or channel_missing:
                details = ", ".join(sorted(missing))
                if channel_missing:
                    details = f"{details}, channel".strip(", ")
                st.warning(f"Cuts were not copied: counting samples do not support {details}.")
            else:
                st.session_state["count_copied_selection"] = (plot_channels, plot_windows)
                st.session_state["count_copy_revision"] += 1
                st.success("Copied cuts and channels. Further plot edits will not change counting.")
        copied = st.session_state.get("count_copied_selection")
        revision = f"{scope}_{st.session_state['count_copy_revision']}"
        # Keep copied channel choices explicit, including channels absent from these samples.
        channels_to_show = sorted(set(channel_options) | (set(copied[0]) if copied else set()))
        channels = (
            st.multiselect(
                "Channels",
                channels_to_show,
                default=copied[0] if copied else channel_options,
                key=f"count_channels_{revision}",
            )
            if channels_to_show
            else []
        )
        windows = _render_variable_sliders(
            variables,
            list(source_frames.values()),
            prefix="count_cut",
            defaults=copied[1] if copied else None,
            revision=revision,
        )
        luminosity = (
            st.number_input(
                "Integrated luminosity [fb⁻¹]",
                min_value=0.001,
                max_value=100_000.0,
                value=1.0,
                key="analysis_luminosity",
            )
            if all_generated
            else 1.0
        )
        background_uncertainty = st.slider(
            "Relative background uncertainty",
            0,
            50,
            10,
            1,
            format="%d%%",
            key="analysis_background_uncertainty",
        )
        calculate = st.button(
            "Run cut-and-count",
            type="primary",
            width="stretch",
            disabled=compatibility_error is not None,
        )

    if not calculate:
        with display:
            st.info(
                "Choose compatible samples to run the count."
                if compatibility_error
                else "Fix the signal region, then run the counting experiment."
            )
        return

    try:
        validate_counting_samples(selected_samples)
        frames = _analysis_frames(
            selected_samples,
            luminosity_fb=float(luminosity),
            expected_yields=True,
            channels=channels,
            windows=windows,
            variables=variables,
        )
        signal_frame = frames[signal.sample_id]
        background_frame = pd.concat(
            [frames[sample.sample_id] for sample in backgrounds], ignore_index=True
        )
        count = summarize_cut_and_count(
            signal_frame,
            background_frame,
            background_uncertainty_fraction=background_uncertainty / 100.0,
        )
    except Exception as error:
        logger.exception("Cut-and-count failed")
        with display:
            st.error(f"Cut-and-count cannot run: {error}")
        return

    with display:
        first, second, third, fourth = st.columns(4)
        first.metric("Expected signal S", f"{count.signal_yield:.3g}")
        second.metric("Expected background B", f"{count.background_yield:.3g}")
        third.metric("S / B", f"{count.signal_to_background:.3g}")
        fourth.metric("Expected Asimov Z", f"{count.asimov_significance:.3g}")
        limit_left, limit_middle, limit_right = st.columns(3)
        limit_left.metric(
            "Approx. expected 95% S limit",
            f"{count.approximate_expected_upper_limit_events:.3g} events",
        )
        limit_middle.metric(
            "Approx. expected μ₉₅",
            f"{count.approximate_expected_signal_strength_limit:.3g}",
        )
        if signal.cross_section_pb is not None:
            cross_section_limit = (
                count.approximate_expected_signal_strength_limit * signal.cross_section_pb
            )
            limit_right.metric("Approx. cross-section limit", f"{cross_section_limit:.3g} pb")
        else:
            limit_right.metric("Cross-section limit", "No physical normalization")
        rows = [
            {
                "role": "signal",
                "sample": signal.label,
                "selected rows": len(signal_frame),
                "expected yield": weighted_yield(signal_frame),
            },
            *[
                {
                    "role": "background",
                    "sample": sample.label,
                    "selected rows": len(frames[sample.sample_id]),
                    "expected yield": weighted_yield(frames[sample.sample_id]),
                }
                for sample in backgrounds
            ],
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.write(
            f"Naive $S/\\sqrt{{B}} = {count.signal_over_sqrt_background:.3g}$; "
            f"with the selected background uncertainty, "
            f"$S/\\sqrt{{B + (\\delta_B B)^2}} = "
            f"{count.approximate_significance_with_systematic:.3g}$."
        )
        st.warning(
            "The 95% limits use a one-sided Gaussian approximation with a three-event "
            "zero-background floor. They are teaching estimates, not CLs or a likelihood fit."
        )
        with st.expander("Reproducible analysis specification"):
            st.json(
                {
                    "signal": signal.sample_id,
                    "backgrounds": [sample.sample_id for sample in backgrounds],
                    "channels": channels,
                    "variable_catalogue": str(variable_catalog_path()),
                    "variables": {name: value.model_dump() for name, value in variables.items()},
                    "counting_windows": windows,
                    "luminosity_fb": luminosity if all_generated else None,
                    "background_uncertainty_fraction": background_uncertainty / 100.0,
                }
            )


def _render_event_explorer() -> None:
    st.header("Event analysis")
    st.caption(
        "Choose any available datasets to compare. Assign signal and background roles only if "
        "you continue to the cut-and-count limit estimate."
    )
    _render_jupyter_entrypoint()
    library = build_sample_library(load_catalog(), _run_root())
    if not library:
        st.info(
            "No samples are available yet. Generate a run or add completed runs to the catalogue."
        )
        return

    plot_selection = _render_sample_plot_controls(library)
    _render_limit_estimate(library, plot_selection=plot_selection)


def _render_sample_plot_controls(
    library: dict[str, AnalysisSample],
) -> tuple[list[str], dict[str, tuple[float, float]]] | None:
    choices = list(library)
    default_datasets = choices[: min(3, len(choices))]
    selected_ids = st.multiselect(
        "Datasets to plot",
        choices,
        default=default_datasets,
        format_func=lambda item: library[item].menu_label,
        help="Select any available sample. Generation details are listed below.",
    )
    if not selected_ids:
        st.info("Choose at least one dataset to make a plot.")
        return

    selected_samples = [library[sample_id] for sample_id in selected_ids]
    _render_sample_details(selected_samples)
    try:
        variable_catalog = load_variable_catalog()
        source_frames = {sample.sample_id: sample.load() for sample in selected_samples}
        variables = variable_catalog.available(selected_samples, source_frames)
    except Exception as error:
        logger.exception("Loading analysis variables or samples failed")
        st.error(f"Cannot load analysis variables or samples: {error}")
        return
    with st.expander("Available analysis variables"):
        st.caption(f"Specification: {variable_catalog_path()} · reloaded on every interaction")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Variable": variable.label,
                        "Column": variable.column,
                        "Definition": variable.description,
                        "Slider step": variable.step,
                    }
                    for variable in variables.values()
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "This list contains the enabled variables shared by the selected processes and "
            "present in every sample. Other quantities can be explored in Jupyter."
        )
    if not variables:
        st.info(
            "These samples have no configured variables in common. Choose other samples "
            "or update the variable specification."
        )
        return
    return _render_dataset_plot(selected_samples, variables, source_frames)


st.set_page_config(page_title="Finding Z", page_icon="🔭", layout="wide")
st.markdown(
    """
    <style>
      header[data-testid="stHeader"] { height: 2.25rem; }
      .block-container { padding-top: 2.5rem; padding-bottom: 33vh; }
      h1 { margin-bottom: 0.1rem; }
      h2 { margin-top: 0.25rem; }
      div[data-testid="stCaptionContainer"] { margin-bottom: 0.15rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    active_catalog = load_catalog()
except Exception as error:
    logger.exception("Loading course catalogue failed")
    st.error(f"Course catalogue failed validation: {error}")
    st.stop()

with st.sidebar:
    st.caption(active_catalog.title)
    st.caption(f"Catalogue: `{catalog_path()}`")

simulation_tab, event_tab = st.tabs(["Simulation", "Analysis"])
with simulation_tab:
    _render_local_simulator()
with event_tab:
    _render_event_explorer()
