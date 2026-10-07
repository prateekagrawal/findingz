from __future__ import annotations

from findingz.beams import com_energy

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
from findingz.catalog import catalog_path, load_catalog, resolve_catalog_path
from findingz import __version__
from findingz.external_models import ufo_digest
from findingz.counting import compare_hypotheses, weighted_yield
from findingz.event_display import render_event_inspector
from findingz.generator_details import render_generator_details, render_run_files
from findingz.hep_pipeline import (
    MAX_HEP_EVENTS,
    HepSimulationConfig,
    hep_run_directory,
    probe_hep_toolchain,
    run_hep_simulation,
    render_delphes_card,
    resolve_detector_card,
)
from findingz.hypotheses import (
    AnalysisSample,
    build_sample_library,
    compatible_counting_backgrounds,
    compatibility_warnings,
    validate_counting_samples,
)
from findingz.run_choices import fresh_config, matching_run, rename_saved_run
from findingz.run_card import RunCardOptions, format_value, parse_edits
from findingz.param_card import ParamCardOptions, parse_edits as parse_param_edits
from findingz.text_cards import TextCardOptions, shower_template, validate_card_text, validate_shower_card
from findingz.run_progress import render_progress_details
from findingz.runs import list_saved_runs
from findingz.notebook_export import notebook_directory, notebook_url, save_notebook, template_path
from findingz.simulation import (
    SimulationRun,
    ToySimulationConfig,
    run_toy_simulation,
)

logger = logging.getLogger("findingz.app")


@st.cache_data(show_spinner=False, ttl=60)
def _installed_pdf_choices(executable):
    from findingz.card_controls import pdf_choices
    return pdf_choices(executable)


@st.cache_data(show_spinner=False)
def _process_card_defaults(executable, model, model_path, process_lines, model_digest, image_id):
    from findingz.card_defaults import prepare_defaults
    return prepare_defaults(executable, model, model_path, process_lines)


def _restore_defaults_button(key, disabled=False):
    st.html("""<style>
    div[class*="st-key-card_restore_"] button {
        min-height: 1.7rem; padding: 0.1rem 0.45rem;
    }
    div[class*="st-key-card_restore_"] button p { font-size: 0.75rem; }
    </style>""")
    with st.container(key=f"card_restore_{key}", width="content"):
        return st.button("Restore defaults", key=key, type="secondary",
                         width="content", disabled=disabled)


def _render_scalar_card_editor(options, key, title, parser, default_loader=None, choice_loader=None):
    if not options.defaults and not options.editable:
        return {}
    if not options.editable:
        st.markdown(f"**{title}**")
        st.caption("Course defaults: " + ", ".join(f"{name} = {value}" for name, value in options.defaults.items()))
        return dict(options.defaults)
    revision = sha256(options.model_dump_json().encode()).hexdigest()[:10]
    prefix = f"{key}_{revision}"
    generation_key = prefix + "_generation"
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(f"**{title}**", width="content")
        if _restore_defaults_button(prefix + "_reset"):
            st.session_state[generation_key] = st.session_state.get(generation_key, 0) + 1
    if options.defaults:
        st.caption("Course defaults: " + ", ".join(f"{name} = {value}" for name, value in options.defaults.items()))
    prefix += f"_{st.session_state.get(generation_key, 0)}"
    native = {}
    try:
        if default_loader is None:
            raise RuntimeError("Default cards are unavailable for this process")
        with st.spinner("Reading this process’s default cards (no events generated)…"):
            native = default_loader()
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        st.warning(f"Parameter editing unavailable: {error}")
    available = set()
    for name in options.editable:
        if name in native:
            try:
                parser(f"{native[name]} = {name}", options)
                available.add(name)
            except ValueError:
                pass
    selection_key = prefix + "_selected"
    selected = [name for name in options.editable
                if name in st.session_state.get(selection_key, []) and name in available]
    from findingz.card_controls import inactive_reason
    choices = choice_loader() if choice_loader else {}
    effective = dict(native)
    effective.update(options.defaults)
    for entry, raw in list(effective.items()):
        if str(raw).lower() in {"true", ".true.", "false", ".false."}:
            effective[entry] = str(raw).lower() in {"true", ".true."}
    for entry in selected:
        default = options.defaults.get(entry, native.get(entry))
        effective[entry] = st.session_state.get(f"{prefix}_{entry}_{default}", effective.get(entry))
    reasons = {}
    if isinstance(options, RunCardOptions):
        reasons = {name: inactive_reason(name, effective) for name in options.editable}
        if not choices.get("lhaid"):
            reasons["lhaid"] = "No installed LHAPDF sets found."
    removed = [name for name in selected if reasons.get(name)]
    for name in removed:
        default = options.defaults.get(name, native.get(name))
        st.session_state.pop(f"{prefix}_{name}_{default}", None)
    selected = [name for name in selected if not reasons.get(name)]
    st.session_state[selection_key] = selected

    def toggle_parameter(name):
        current = list(st.session_state.get(selection_key, []))
        if name in current:
            current.remove(name)
        else:
            current.append(name)
        st.session_state[selection_key] = current

    with st.container(horizontal=True):
        for name in options.editable:
            st.button(name, key=f"{prefix}_choose_{name}",
                      type="primary" if name in selected else "secondary",
                      disabled=name not in available or bool(reasons.get(name)),
                      help="Unavailable or fixed in this model/process card." if name not in available
                           else reasons.get(name) or "Click to select or restore the default.",
                      on_click=toggle_parameter, args=(name,))
    if not selected:
        return dict(options.defaults)
    result = dict(options.defaults)
    st.html("""<style>
    div[class*="st-key-card_table_"],
    div[class*="st-key-card_table_"] [data-testid="stVerticalBlock"] { gap: 0.25rem; }
    div[class*="st-key-card_table_"] [data-testid="stMarkdownContainer"],
    div[class*="st-key-card_table_"] [data-testid="stCaptionContainer"],
    div[class*="st-key-card_table_"] p {
        margin: 0 !important; line-height: 1.3;
    }
    div[class*="st-key-card_table_"] [data-testid="stTextInput"] input,
    div[class*="st-key-card_table_"] [data-testid="stNumberInput"] input {
        min-height: 1.9rem; height: 1.9rem; padding: 0.15rem 0.5rem;
    }
    div[class*="st-key-card_table_"] [data-baseweb="input"] { min-height: 1.9rem; }
    div[class*="st-key-card_table_"] [data-testid="stNumberInput"] button { display: none; }
    div[class*="st-key-card_table_"] [data-testid="stHorizontalBlock"] {
        display: grid; grid-template-columns: 145px 135px 95px minmax(0, 1fr);
        align-items: center; gap: 8px; padding: 4px 0;
        border-bottom: 1px solid rgba(128, 128, 128, 0.15);
    }
    div[class*="st-key-card_table_"] [data-testid="stColumn"] {
        width: 100% !important; min-width: 0 !important;
        display: flex; flex-direction: column; justify-content: center;
    }
    div[class*="st-key-card_table_"] [data-baseweb="input"],
    div[class*="st-key-card_table_"] [data-baseweb="select"] > div {
        min-height: 32px; height: 32px;
    }
    @media (max-width: 700px) {
        div[class*="st-key-card_table_"] [data-testid="stHorizontalBlock"] {
            grid-template-columns: 1.2fr 1.1fr 0.8fr 2fr;
        }
    }
    </style>""")
    with st.container(key=f"card_table_{prefix}"):
        headers = st.columns([1.15, 1.05, 0.85, 6.95], gap="small")
        for column, label in zip(headers, ["Parameter", "Value", "Default", "Description"]):
            column.caption(label)
        valid = True
        for name in selected:
            default = options.defaults.get(name, native.get(name))
            if default is None:
                st.error(f"{name}: no editable default exists in this process’s card.")
                valid = False
                continue
            name_col, value_col, default_col, description_col = st.columns([1.15, 1.05, 0.85, 6.95], vertical_alignment="center", gap="small")
            name_col.markdown(f"`{name}`")
            baseline = parser(f"{default} = {name}", options)[name]
            widget_key = f"{prefix}_{name}_{default}"
            reason = inactive_reason(name, effective) if isinstance(options, RunCardOptions) else None
            menu = options.choices.get(name)
            if name in {"pdlabel", "lhaid"} and isinstance(options, RunCardOptions):
                installed = dict(choices.get(name, {}))
                if menu is not None:
                    installed = {v: label for v, label in menu.items() if v in installed}
                menu = installed
                if name != "lhaid" and str(baseline) not in menu:
                    menu = {str(baseline): f"{baseline} (default)", **menu}
                if name == "lhaid" and not choices.get(name):
                    reason = "No installed LHAPDF sets found."
            if menu is not None:
                values = list(menu)
                if name != "lhaid" and str(baseline) not in menu:
                    values.insert(0, str(baseline))
                text = value_col.selectbox(f"New value for {name}", values,
                    index=values.index(str(baseline)) if str(baseline) in values else None, format_func=lambda v, m=menu: m.get(v, f"{v} (default)"),
                    key=widget_key, label_visibility="collapsed", disabled=bool(reason), help=reason)
            elif isinstance(baseline, bool):
                text = str(value_col.selectbox(f"New value for {name}", [False, True],
                    index=int(baseline), format_func=lambda value: "True" if value else "False",
                    key=widget_key, label_visibility="collapsed", disabled=bool(reason)))
            elif isinstance(baseline, (int, float)):
                text = str(value_col.number_input(f"New value for {name}", value=baseline,
                    key=widget_key, label_visibility="collapsed", disabled=bool(reason),
                    help=reason, format="%d" if isinstance(baseline, int) else "%g"))
            else:
                text = value_col.text_input(f"New value for {name}", value=str(default),
                    key=widget_key, label_visibility="collapsed", help="Leave blank to use the default.")
            default_col.caption(str(default))
            from findingz.card_descriptions import parameter_description
            description_col.caption(options.descriptions.get(name, parameter_description(name)) + (" " + reason if reason else ""))
            try:
                if text is None:
                    if reason:
                        text = str(default)
                    else:
                        raise ValueError("Choose an installed PDF set before running")
                if any(char in text for char in "\n\r=#!"):
                    raise ValueError("Enter a single value, without a parameter name or comment")
                baseline = parser(f"{default} = {name}", options)[name]
                value = parser(f"{text} = {name}", options)[name] if text.strip() else baseline
                if value != baseline and not reason:
                    result[name] = value

            except ValueError as error:
                st.error(f"{name}: {error}")
                valid = False
    if isinstance(options, RunCardOptions) and result.get("pdlabel", effective.get("pdlabel")) == "lhapdf":
        pdf_id = str(result.get("lhaid", options.defaults.get("lhaid", native.get("lhaid"))))
        if pdf_id not in choices.get("lhaid", {}):
            st.error("Select lhaid and choose an installed PDF set before running with LHAPDF.")
            valid = False
    return result if valid else None


def _render_run_card_editor(options: RunCardOptions, key: str, default_loader=None, choice_loader=None):
    if not options.defaults and not options.editable:
        return {}
    with st.container(border=True):
        return _render_scalar_card_editor(options, "run_card_" + key, "Run-card settings",
                                          parse_edits, default_loader, choice_loader)


def _render_param_card_editor(options: ParamCardOptions, key: str, default_loader=None):
    if not options.defaults and not options.editable:
        return {}
    with st.container(border=True):
        return _render_scalar_card_editor(options, "param_card_" + key, "Model parameters",
                                          parse_param_edits, default_loader)


def _render_text_card_editor(options: TextCardOptions, title: str, key: str, source, default_loader,
                             validator=validate_card_text):
    if not options.path and not options.editable:
        return None, True
    with st.container(border=True):
        return _render_text_card_contents(options, title, key, source, default_loader, validator)


def _render_text_card_contents(options, title, key, source, default_loader, validator):
    """An unopened editor uses the existing pipeline defaults, preserving run identity."""
    revision = sha256(options.model_dump_json().encode()).hexdigest()[:10]
    edit_key = f"edit_{key}_{revision}"
    generation_key = f"text_generation_{key}_{revision}"

    def discard_draft():
        if not st.session_state.get(edit_key, False):
            st.session_state[generation_key] = st.session_state.get(generation_key, 0) + 1

    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        editing = options.editable and st.checkbox(
            f"Edit {title}", key=edit_key, on_change=discard_draft, width="content")
        if options.editable and _restore_defaults_button(f"restore_{key}_{revision}", disabled=not editing):
            st.session_state[generation_key] = st.session_state.get(generation_key, 0) + 1
    if options.editable:
        st.caption("Edits apply to the next run while checked. Unchecking discards edits and uses "
                   "the course/default card. Cards are saved with the run when you generate events.")
    if not options.path and not editing:
        return None, True
    try:
        original = (resolve_catalog_path(options.path, source).read_text()
                    if options.path else default_loader())
        validator(original)
        if editing:
            content_id = sha256(original.encode()).hexdigest()[:10]
            text = st.text_area(title, value=original, height=300,
                                key=f"text_{key}_{revision}_{content_id}_{st.session_state.get(generation_key, 0)}",
                                help="The entire card is used. Keep required output settings and "
                                     "file references valid for the installed simulation tools.")
            validator(text)
        else:
            text = original
            st.caption(f"{title}: using the course-supplied card")
        return (text if options.path or text != original else None), True
    except (OSError, ValueError, RuntimeError) as error:
        st.error(f"{title}: {error}")
        return None, False


def _luminosity_input(key: str) -> float:
    """Display selectable units; return fb^-1 for weights and saved notebooks."""
    factors = {"fb⁻¹": 1.0, "pb⁻¹": 1e-3, "nb⁻¹": 1e-6}
    value_column, unit_column = st.columns([2, 1])
    with unit_column:
        unit = st.selectbox("Luminosity unit", list(factors), index=2, key=f"{key}_unit")
    previous = st.session_state.get(f"{key}_display_unit", "fb⁻¹")
    if previous != unit and key in st.session_state:
        st.session_state[key] *= factors[previous] / factors[unit]
    st.session_state[f"{key}_display_unit"] = unit
    with value_column:
        value = st.number_input(
            "Integrated luminosity", min_value=0.0,
            value=20e-6 / factors[unit], format="%.6g", key=key,
            help="Changing units preserves the luminosity. Enter a new value to change the exposure.",
        )
    return float(value) * factors[unit]


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
        center_of_mass_energy = com_energy(collider_entry.beam_energy_gev, collider_entry.beam2_energy_gev)
        energy_label = (
            f"{center_of_mass_energy / 1_000:g} TeV"
            if center_of_mass_energy >= 1_000
            else f"{center_of_mass_energy:g} GeV"
        )
        detector_id = "none"
        detector_card = "none"
        detector_description = "Parton level; no detector simulation"
        output_detail = "standard"
        shower_card_text = detector_card_text = None
        extra_cards_valid = True
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
        if model_entry.ufo_path:
            try:
                ufo_digest(resolve_catalog_path(model_entry.ufo_path, catalog._source))
            except (ValueError, OSError) as error:
                st.error(f"Course model unavailable: {error}")
                return
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
            beam2_energy = collider_entry.beam2_energy_gev
            settings = st.columns(3 + int(beam2_energy is not None) + int(is_full))
            with settings[0]:
                events = st.number_input(
                    "Events", min_value=100, max_value=MAX_HEP_EVENTS,
                    value=1_000, step=100, key="hep_events",
                    help="Number of hard-scattering events to generate.",
                )
            with settings[1]:
                seed = st.number_input(
                    "Seed", min_value=1, max_value=900_000_000,
                    value=225, key="hep_seed",
                    help="Random seed for reproducible generation.",
                )
            with settings[2]:
                beam_energy = st.number_input(
                    "Beam 1 [GeV]" if beam2_energy is not None else "Energy / beam [GeV]",
                    min_value=10.0, max_value=50_000.0,
                    value=collider_entry.beam_energy_gev,
                    step=0.1 if collider_entry.beam_type == "ee" else 500.0,
                    key=f"beam_energy_{collider_id}",
                    help=f"Collider preset: {collider_entry.beam_energy_gev:g} GeV per beam"
                         if beam2_energy is None else
                         f"Beam 1 preset: {collider_entry.beam_energy_gev:g} GeV.",
                )
            if beam2_energy is not None:
                with settings[3]:
                    beam2_energy = st.number_input(
                        "Beam 2 [GeV]", min_value=10.0, max_value=50_000.0,
                        value=beam2_energy, key=f"beam2_energy_{collider_id}",
                        help=f"Beam 2 preset: {collider_entry.beam2_energy_gev:g} GeV.",
                    )
            if is_full:
                with settings[-1]:
                    detail_label = st.selectbox(
                        "Detector output", ["Compact (recommended)", "Full"],
                        help=(
                            "Compact (default) saves reconstructed leptons, photons, jets "
                            "and missing energy. Full also saves generator particles, "
                            "tracks, calorimeter towers and particle-flow collections, "
                            "producing a larger ROOT file."
                        ),
                    )
                    output_detail = "advanced" if detail_label == "Full" else "standard"
            def native_defaults():
                model_path = (str(resolve_catalog_path(model_entry.ufo_path, catalog._source))
                              if model_entry.ufo_path else None)
                return _process_card_defaults(
                    str(toolchain.mg5_executable), model_entry.madgraph_name or model_id,
                    model_path, tuple(process_entry.madgraph_lines),
                    ufo_digest(model_path) if model_path else None, toolchain.image_id,
                )
            run_card_overrides = _render_run_card_editor(
                process_entry.run_card if process_entry.run_card is not None else catalog.run_card,
                f"{collider_id}_{model_id}_{process_id}", lambda: native_defaults()[0],
                lambda: _installed_pdf_choices(str(toolchain.mg5_executable)),
            )
            param_options = process_entry.param_card
            if param_options is None:
                param_options = model_entry.param_card
            if param_options is None:
                param_options = catalog.param_card
            param_card_overrides = _render_param_card_editor(
                param_options, f"{collider_id}_{model_id}_{process_id}", lambda: native_defaults()[1],
            )
            if is_full:
                card_key = f"{collider_id}_{model_id}_{process_id}"
                shower_options = process_entry.shower_card or catalog.shower_card
                detector_options = process_entry.detector_card or catalog.detector_card
                shower_card_text, shower_valid = _render_text_card_editor(
                    shower_options, "Pythia shower card", f"shower_{card_key}", catalog._source,
                    lambda: shower_template(toolchain.mg5_executable).read_text(),
                    validator=validate_shower_card,
                )
                detector_card_text, detector_valid = _render_text_card_editor(
                    detector_options, "Delphes detector card", f"detector_{card_key}_{output_detail}",
                    catalog._source,
                    lambda: render_delphes_card(resolve_detector_card(
                        HepSimulationConfig(detector_card=detector_card), toolchain).read_text(), output_detail),
                )
                extra_cards_valid = shower_valid and detector_valid
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
            disabled=(job_active or not backend_ready or run_card_overrides is None
                      or param_card_overrides is None or not extra_cards_valid),
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
                model=model_entry.madgraph_name or model_id,
                model_ufo_path=(str(resolve_catalog_path(model_entry.ufo_path, catalog._source))
                                if model_entry.ufo_path else None),
                run_mode="full" if is_full else "madgraph",
                beam_energy_gev=beam_energy,
                beam2_energy_gev=beam2_energy,
                detector_id=detector_id,
                detector_card=detector_card,
                output_detail=output_detail,
                run_card_overrides=run_card_overrides,
                param_card_overrides=param_card_overrides,
                shower_card_text=shower_card_text,
                detector_card_text=detector_card_text,
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
        accepted = manifest.get("analysis_events", manifest.get("accepted_events", manifest.get("accepted_dileptons")))
        metric_columns[1].metric("Available analysis events", accepted)
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
    st.divider()
    st.subheader("Continue in Jupyter")
    name = st.text_input("Notebook name (optional)", key="notebook_name")
    snapshot = {key: st.session_state.get(f"notebook_{key}") for key in ("plot", "count")}
    can_open = bool(os.environ.get("FINDINGZ_NOTEBOOK_URL_PREFIX", "").strip())
    left, right = st.columns(2)
    current = left.button("Save current analysis notebook", disabled=not any(snapshot.values()))
    blank = right.button("Save blank template notebook")
    st.caption(f"Notebooks saved to: {notebook_directory()}")
    st.caption(f"Template: {template_path()}")
    st.caption("Creates a new editable notebook, without overwriting earlier work. Run its cells to reproduce the analysis.")
    if can_open:
        st.caption("Save a notebook, then use the JupyterLab link below to open it. Duplicate names get a numbered suffix.")
    if not can_open:
        st.caption("A JupyterLab link is not configured here. Save the notebook, then open the displayed path in JupyterLab.")
    if current or blank:
        st.session_state.pop("notebook_save_error", None)
        try:
            saved = save_notebook(name, snapshot if current else None)
            st.session_state["saved_analysis_notebook"] = str(saved)
        except (OSError, ValueError, TypeError) as error:
            st.session_state["notebook_save_error"] = f"Could not save the notebook: {error}"
    error = st.session_state.get("notebook_save_error")
    if error:
        st.error(error)
    saved = st.session_state.get("saved_analysis_notebook")
    if saved:
        if error:
            st.caption(f"Previously saved notebook (unchanged): {saved}")
        else:
            st.success(f"Saved notebook: {saved}")
        settings_file = Path(saved).with_suffix(".settings.json")
        if settings_file.is_file():
            st.caption(f"Saved settings: {settings_file.name}. Keep this file with the notebook when downloading or submitting it.")
        url = notebook_url(saved)
        if url:
            st.link_button("Open saved notebook in JupyterLab", url)
        else:
            st.info("Open this saved file in your existing JupyterLab file browser.")


def _sample_config_summary(sample: AnalysisSample) -> str:
    if sample.kind == "prepared":
        return "Synthetic sample · no physical cross-section normalization"
    config = sample.config
    mode = "Full pipeline" if config.get("run_mode") == "full" else "MadGraph only"
    energy = config.get("beam_energy_gev")
    energy_text = f" · {com_energy(float(energy), config.get('beam2_energy_gev')):g} GeV √s" if isinstance(energy, int | float) else ""
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
    messages = compatibility_warnings(samples)
    if messages:
        st.warning(" ".join(messages))
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
            _luminosity_input("plot_luminosity")
            if generated and normalization == "Expected yields"
            else 1.0
        )

    st.session_state["notebook_plot"] = {
        "samples": [sample.sample_id for sample in selected_samples],
        "observable": observable, "channels": channels, "windows": windows,
        "variables": {name: value.model_dump() for name, value in variables.items()},
        "expected_yields": normalization == "Expected yields", "luminosity_fb": float(luminosity),
        "sample_configs": {sample.sample_id: sample.config for sample in selected_samples},
    }
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
            frame = frame.loc[np.isfinite(pd.to_numeric(frame[column], errors="coerce"))]
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


def _render_discovery_estimate(
    library: dict[str, AnalysisSample],
    *,
    plot_selection: tuple[list[str], dict[str, tuple[float, float]]] | None,
) -> None:
    st.divider()
    st.subheader("Cut-and-count hypothesis comparison")
    st.caption(
         "Compare two complete predictions for the same final state: null versus alternative. Neither is added to the other. "
        "These choices are independent of the plot. "
        "Define cuts here, or copy the current plot cuts once and edit them independently."
    )
    role_samples = list(library.values())
    if len(role_samples) < 2:
        st.info("At least two samples are needed to compare complete predictions.")
        return

    role_ids = list(library)
    role_columns = st.columns(2)
    with role_columns[0]:
        null_id = st.selectbox(
            "1. Null prediction", role_ids, index=None,
            format_func=lambda item: library[item].menu_label,
            key="count_null", placeholder="Choose the complete null prediction",
        )
    if null_id is None:
        st.info("Choose a null prediction first. Neither prediction is selected automatically.")
        return
    null_sample = library[null_id]
    alternative_options = compatible_counting_backgrounds(null_sample, library)
    previous = st.session_state.get("count_alternative")
    if previous is not None and previous not in alternative_options:
        st.session_state["count_alternative"] = None
        st.info("Cleared the alternative because it no longer matches the null configuration.")
    with role_columns[1]:
        alternative_id = st.selectbox(
            "2. Complete alternative prediction", alternative_options, index=None,
            format_func=lambda item: library[item].menu_label,
            key="count_alternative", disabled=not alternative_options,
            placeholder="Choose the complete alternative",
            help="Includes all backgrounds as well as the effect being tested. The two samples are never added.",
        )
    if not alternative_options:
        st.info("No compatible alternative is available. Match the collision setup and simulation level, and supply normalization metadata.")
        return
    if alternative_id is None:
        st.info("Choose a complete alternative prediction to continue.")
        return
    alternative = library[alternative_id]
    selected_samples = [null_sample, alternative]
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
            _luminosity_input("analysis_luminosity")
            if all_generated
            else 1.0
        )
        background_uncertainty = st.slider(
            "Relative null-prediction uncertainty",
            0,
            50,
            0,
            1,
            format="%d%%",
            key="comparison_null_uncertainty",
            help="At 0%, use a known-null Poisson likelihood. Otherwise profile the null rate with a Gaussian constraint of this relative width. Finite Monte Carlo uncertainty is not included.",
        )
        calculate = st.button(
            "Run cut-and-count",
            type="primary",
            width="stretch",
            disabled=compatibility_error is not None,
        )

    if compatibility_error is None:
        st.session_state["notebook_count"] = {
            "mode": "hypothesis_comparison", "null": null_id, "alternative": alternative_id,
            "channels": channels, "windows": windows,
            "variables": {name: value.model_dump() for name, value in variables.items()},
            "luminosity_fb": float(luminosity), "expected_yields": True,
            "null_uncertainty_fraction": background_uncertainty / 100.0,
            "sample_configs": {sample.sample_id: sample.config for sample in selected_samples},
        }
    if not calculate:
        with display:
            st.info(
                "Choose compatible samples to run the count."
                if compatibility_error
                else "Fix the selection, then compare the predicted counts."
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
        null_frame = frames[null_id]
        alternative_frame = frames[alternative_id]
        count = compare_hypotheses(
            null_frame, alternative_frame,
            null_uncertainty_fraction=background_uncertainty / 100.0,
        )
    except Exception as error:
        logger.exception("Cut-and-count failed")
        with display:
            st.error(f"Cut-and-count cannot run: {error}")
        return

    with display:
        first, second, third = st.columns(3)
        number = lambda value: f"{value:,.2f}"
        first.metric("Null prediction", number(count.null_yield), help="Predicted selected events under the null hypothesis at this luminosity.")
        second.metric("Alternative prediction", number(count.alternative_yield), help="Complete predicted selected events, including backgrounds and the effect being tested.")
        third.metric("Excess / deficit (alternative − null)", number(count.difference))
        st.write(f"Null: **{number(count.null_yield)}** events; alternative: **{number(count.alternative_yield)}** events. "
                 f"The difference is **{number(count.difference)}** events. These predictions are not added.")
        if count.signed_significance is None:
            st.info("Approximate expected separation is undefined: the null predicts zero selected events. "
                    "Zero simulated events do not establish an exactly zero physical rate.")
        else:
            direction = "excess" if count.difference > 0 else "deficit" if count.difference < 0 else "no difference"
            label = "Expected discovery sensitivity" if count.difference >= 0 else "Expected deficit sensitivity"
            st.write(f"**{label}: {count.signed_significance:+.2f} σ ({direction}).**")
        with st.expander("What does this sensitivity mean? · Statistics reading"):
            st.markdown(
                "This uses the **Asimov approximation**: pretend the observed count equals "
                "the alternative's expected count, without random fluctuations. It estimates "
                "sensitivity, not a discovery measured from data. Actual observed counts are "
                "integers; for a few events, use an exact Poisson test with the appropriate "
                "background uncertainties. A deficit is not an excess discovery.\n\n"
                "**Start here:** [PDG Statistics review](https://pdg.lbl.gov/2025/reviews/rpp2025-rev-statistics.pdf), "
                "sections 40.1 and 40.3: likelihoods, hypothesis tests, p-values and significance. "
                "A p-value is not the probability that the null hypothesis is true.\n\n"
                "**Calculation details:** [Cowan et al., Asymptotic formulae for likelihood-based tests of new physics]"
                "(https://arxiv.org/abs/1007.1727), especially the Asimov construction and counting experiment."
            )
        if count.null_uncertainty_fraction == 0:
            st.latex(r"Z_A = \operatorname{sgn}(N_1-N_0)\sqrt{2[N_1\ln(N_1/N_0)-N_1+N_0]}")
        else:
            st.caption("The Poisson likelihood profiles the null rate with a Gaussian constraint centred on N₀, of width δ₀N₀.")
        st.caption("N₀ is the null count and N₁ the complete alternative count. The sign distinguishes an excess from a deficit. "
                   "This is expected sensitivity, not a significance measured from data. It is not an exact Poisson p-value.")
        if count.null_yield > 0 and (count.null_yield < 10 or count.alternative_yield < 10):
            st.warning("For small counts, the Asimov sigma is only an approximation. An observed integer count requires a Poisson tail calculation.")
        st.caption("Both samples must describe the same final states and acceptance. Configuration matching alone cannot establish a valid physics comparison.")
        st.caption("Finite-simulation uncertainties are not included. Comparing two samples of the same physics is not a discovery test, even if the displayed separation is large.")
        with st.expander("Details: sample yields and statistical assumptions"):
            st.dataframe(pd.DataFrame([
                {"role": role, "sample": sample.label, "selected rows": len(frames[sample.sample_id]),
                 "expected yield": weighted_yield(frames[sample.sample_id])}
                for role, sample in [("null", null_sample), ("alternative", alternative)]
            ]), hide_index=True, width="stretch")
            st.caption("Selected rows count simulated events; yields include cross-section and luminosity weights. "
                       "Finite-simulation uncertainties are not included: differences between two simulations of the same physics are not evidence of discovery.")
        with st.expander("Reproducible analysis specification"):
            st.json(
                {
                    "mode": "hypothesis_comparison",
                    "null": null_id, "alternative": alternative_id,
                    "channels": channels,
                    "variable_catalogue": str(variable_catalog_path()),
                    "variables": {name: value.model_dump() for name, value in variables.items()},
                    "counting_windows": windows,
                    "luminosity_fb": luminosity if all_generated else None,
                    "null_uncertainty_fraction": background_uncertainty / 100.0,
                }
            )


def _render_event_explorer() -> None:
    st.header("Event analysis")
    st.caption(
        "Choose any available datasets to compare. Choose null and alternative predictions only if "
        "you continue to the cut-and-count comparison."
    )
    st.session_state["notebook_plot"] = None
    st.session_state["notebook_count"] = None
    try:
        library = build_sample_library(load_catalog(), _run_root())
    except (ValueError, OSError) as error:
        st.error(f"Cannot load course samples: {error}")
        return
    if not library:
        st.info(
            "No samples are available yet. Generate a run or add completed runs to the catalogue."
        )
        _render_jupyter_entrypoint()
        return

    plot_selection = _render_sample_plot_controls(library)
    _render_discovery_estimate(library, plot_selection=plot_selection)
    _render_jupyter_entrypoint()


def _render_sample_plot_controls(
    library: dict[str, AnalysisSample],
) -> tuple[list[str], dict[str, tuple[float, float]]] | None:
    choices = list(library)
    selected_ids = st.multiselect(
        "Datasets to plot",
        choices,
        default=[],
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
    st.caption(f"FindingZ {__version__} · Catalogue: `{catalog_path()}`")

simulation_tab, event_tab = st.tabs(["Simulation", "Analysis"])
with simulation_tab:
    _render_local_simulator()
with event_tab:
    _render_event_explorer()
