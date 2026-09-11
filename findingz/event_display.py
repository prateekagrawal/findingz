"""Optional, read-only inspection of reconstructed Delphes events."""

import gzip
import math
import random
import re
from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure

COLLECTIONS = {"Electron": "Electrons", "Muon": "Muons", "Photon": "Photons", "Jet": "Jets"}


def lhe_events(path: Path):
    """Stream events from plain or compressed LHE, ignoring weights/header XML."""
    opener = gzip.open if path.suffix == ".gz" else open
    # Generator headers can contain unescaped XML characters in embedded cards.
    # Read only the event's numeric record, not the header or nested reweight tags.
    with opener(path, "rt") as source:
        lines = None
        for raw in source:
            for part in re.split(r"(<event(?:\s[^>]*)?>|</event>)", raw):
                line = part.strip()
                if re.fullmatch(r"<event(?:\s[^>]*)?>", line):
                    lines = []
                elif line == "</event>" and lines is not None:
                    yield "\n".join(lines)
                    lines = None
                elif lines is not None and line and not line.startswith(("<", "#")):
                    lines.append(line)


def read_lhe_event(path: Path, index: int) -> pd.DataFrame:
    if index < 0:
        raise IndexError("Event number is outside this sample")
    for number, text in enumerate(lhe_events(path)):
        if number != index:
            continue
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        n_particles = int(lines[0].split()[0])
        rows = []
        for position, line in enumerate(lines[1 : n_particles + 1], 1):
            fields = line.split()
            pid, status = int(fields[0]), int(fields[1])
            if status != 1:
                continue
            px, py, pz, energy = [
                float(v.replace("D", "E").replace("d", "e")) for v in fields[6:10]
            ]
            pt = math.hypot(px, py)
            category = {
                11: "Electron",
                13: "Muon",
                15: "Tau",
                22: "Photon",
                21: "Gluon",
                12: "Neutrino",
                14: "Neutrino",
                16: "Neutrino",
            }.get(abs(pid), "Quark" if 1 <= abs(pid) <= 6 else "Other particle")
            rows.append(
                {
                    "Object": category,
                    "Index": position,
                    "PDG ID": pid,
                    "pT [GeV]": pt,
                    "η": math.asinh(pz / pt) if pt else float("nan"),
                    "φ [rad]": math.atan2(py, px) if pt else float("nan"),
                    "Energy [GeV]": energy,
                }
            )
        return pd.DataFrame(
            rows, columns=["Object", "Index", "PDG ID", "pT [GeV]", "η", "φ [rad]", "Energy [GeV]"]
        )
    raise IndexError("Event number is outside this sample")


def event_controls(count: int, key: str) -> int | None:
    import streamlit as st

    def randomize():
        st.session_state[key] = random.randint(1, count)
        st.session_state[f"shown_{key}"] = st.session_state[key]

    number = st.number_input("Event number", min_value=1, max_value=count, step=1, key=key)
    show = st.button("Show event", key=f"show_{key}", width="stretch")
    st.button("Random event", key=f"random_{key}", on_click=randomize, width="stretch")
    if show:
        st.session_state[f"shown_{key}"] = int(number)
    return st.session_state.get(f"shown_{key}")


def render_lhe_inspector(path: Path, run_id: str) -> None:
    import streamlit as st

    @st.cache_data(show_spinner=False, max_entries=32)
    def event_count(filename: str, size: int, modified: int) -> int:
        return sum(1 for _ in lhe_events(Path(filename)))

    stat = path.stat()
    count = event_count(str(path), stat.st_size, stat.st_mtime_ns)
    if not count:
        st.info("This LHE file contains no events.")
        return
    controls, plot = st.columns([1, 2.4], gap="large")
    with controls:
        number = event_controls(count, f"lhe_event_number_{run_id}")
        st.caption("Parton level · outgoing particles only. No shower or detector simulation.")
    if number is None:
        return
    objects = read_lhe_event(path, int(number) - 1)
    controls.caption(f"Event {number} / {count} · before analysis cuts")
    with plot:
        if objects.empty:
            st.info("No outgoing particles in this event.")
        else:
            st.pyplot(event_figure(objects, parton_level=True), width=700)
    with st.expander("Particle details", expanded=False):
        st.dataframe(objects, hide_index=True, width="stretch")
        st.caption(
            "Marker area grows with pT, capped at 200 GeV. Quarks and gluons are "
            "partons, not reconstructed jets. Neutrinos are shown explicitly; no detector "
            "missing momentum is inferred. Particles with zero pT remain in the table "
            "but have undefined η/φ and are omitted from the plot. Reading a compressed "
            "event scans the file up to that event; no saved data or selections are changed."
        )


def read_event(tree, index: int) -> tuple[pd.DataFrame, list[tuple[float, float]], list[str]]:
    if not 0 <= index < tree.num_entries:
        raise IndexError("Event number is outside this sample")
    keys = {name.rsplit("/", 1)[-1] for name in tree.keys()}  # noqa: SIM118 -- ROOT tree API
    rows, missing = [], []
    for collection in COLLECTIONS:
        required = [f"{collection}.{field}" for field in ("PT", "Eta", "Phi")]
        if not set(required) <= keys:
            missing.append(collection)
            continue
        fields = required + ([f"{collection}.Charge"] if f"{collection}.Charge" in keys else [])
        arrays = tree.arrays(fields, entry_start=index, entry_stop=index + 1, library="ak")
        for i, pt in enumerate(arrays[required[0]][0]):
            rows.append(
                {
                    "Object": collection,
                    "Index": i + 1,
                    "pT [GeV]": float(pt),
                    "η": float(arrays[required[1]][0][i]),
                    "φ [rad]": float(arrays[required[2]][0][i]),
                    "Charge": float(arrays[fields[3]][0][i]) if len(fields) == 4 else None,
                }
            )
    met = []
    if {"MissingET.MET", "MissingET.Phi"} <= keys:
        arrays = tree.arrays(
            ["MissingET.MET", "MissingET.Phi"],
            entry_start=index,
            entry_stop=index + 1,
            library="ak",
        )
        met = [
            (float(pt), float(phi))
            for pt, phi in zip(arrays["MissingET.MET"][0], arrays["MissingET.Phi"][0], strict=True)
        ]
    return (
        pd.DataFrame(rows, columns=["Object", "Index", "pT [GeV]", "η", "φ [rad]", "Charge"]),
        met,
        missing,
    )


def event_figure(objects: pd.DataFrame, *, parton_level: bool = False) -> Figure:
    figure = Figure(figsize=(7, 4), facecolor="white", layout="constrained")
    axes = figure.subplots()
    axes.set_facecolor("white")
    categories = dict(COLLECTIONS)
    if parton_level:
        categories.update(
            {name: name for name in ["Tau", "Neutrino", "Quark", "Gluon", "Other particle"]}
        )
    for i, (collection, label) in enumerate(categories.items()):
        marker = ["o", "s", "*", "^", "D", "x", "v", "P", "h"][i]
        color = [
            "#0072B2",
            "#D55E00",
            "#009E73",
            "#CC79A7",
            "#332288",
            "#666666",
            "#AA4499",
            "#882255",
            "#117733",
        ][i]
        subset = objects[objects["Object"] == collection]
        subset = subset[
            subset[["pT [GeV]", "η", "φ [rad]"]]
            .apply(lambda column: column.map(math.isfinite))
            .all(axis=1)
        ]
        if not subset.empty:
            axes.scatter(
                subset["η"],
                subset["φ [rad]"],
                s=20 + 3 * subset["pT [GeV]"].clip(0, 200),
                marker=marker,
                color=color,
                alpha=0.8,
                label=label,
            )
    axes.set(
        xlabel="Pseudorapidity η",
        ylabel="Azimuth φ [rad]",
        ylim=(-math.pi, math.pi),
        title="Outgoing LHE particles (parton level)"
        if parton_level
        else "Reconstructed objects (not detector geometry)",
    )
    axes.grid(alpha=0.2)
    if axes.collections:
        axes.legend(loc="best", markerscale=0.5)
    return figure


def render_event_inspector(run_dir: Path, manifest: dict) -> None:
    import streamlit as st

    with st.expander("Inspect an event", expanded=False):
        stages = manifest.get("stages", {})
        detector = stages.get("detector_root")
        relative = detector or stages.get("matrix_element")
        if not relative:
            st.caption("Event inspection requires retained Delphes ROOT or MadGraph LHE output.")
            return
        path = (run_dir / relative).resolve()
        if not path.is_relative_to(run_dir.resolve()) or not path.is_file():
            st.warning("The event file is not available for this run.")
            return
        try:
            if not detector:
                render_lhe_inspector(path, run_dir.name)
                return
            import uproot

            with uproot.open(path) as source:
                tree = source["Delphes"]
                count = tree.num_entries
                if not count:
                    st.info("This file contains no events.")
                    return
                controls, plot = st.columns([1, 2.4], gap="large")
                with controls:
                    number = event_controls(count, f"event_number_{run_dir.name}")
                    st.caption("Reconstructed Delphes objects, before analysis cuts.")
                if number is None:
                    return
                objects, met, missing = read_event(tree, int(number) - 1)
            controls.caption(
                f"Event {number} of {count} in the original detector sample, before analysis "
                "cuts. Random selection is uniform and may pick an empty event."
            )
            with plot:
                if objects.empty:
                    st.info("No electrons, muons, photons or jets in the available collections.")
                else:
                    st.pyplot(event_figure(objects), width=700)
            with st.expander("Object details", expanded=False):
                st.caption(
                    "Marker area grows with pT and is capped at 200 GeV. "
                    "Markers are objects, not tracks or jet boundaries. "
                    "Collections may overlap; no additional object cleaning is applied."
                )
                st.dataframe(objects, hide_index=True, width="stretch")
            if met:
                for pt, phi in met:
                    controls.caption(f"Missing pT: {pt:.2f} GeV · φ = {phi:.3f} rad")
            else:
                controls.caption("Missing pT unavailable.")
            if missing:
                st.caption("Collections not retained/available: " + ", ".join(missing))
            st.caption(
                "Objects are defined by this run's Delphes card. This view does not "
                "change any analysis selections."
            )
        except Exception as error:
            import logging

            logging.getLogger(__name__).exception("Event inspection failed")
            st.warning(
                f"Could not inspect this event: {error}. Other run results remain available."
            )
