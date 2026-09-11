"""Retain native generator documentation without keeping the build tree."""

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageChops


def diagram_preview(path: Path) -> Image.Image:
    """Display old transparent previews on white without modifying saved artifacts."""
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
        paper = Image.new("RGBA", rgba.size, "white")
        preview = Image.alpha_composite(paper, rgba).convert("RGB")
    ink = ImageChops.difference(preview, Image.new("RGB", preview.size, "white")).convert("L")
    ink = ink.point(lambda value: 255 if value > 25 else 0)
    width, height = preview.size
    top, bottom = 0, height
    # Native printable pages have isolated page numbering and a distant footer.
    # Remove only small, separated marginal bands, never a fixed slice of diagrams.
    bands = []
    for y in range(height):
        if ink.crop((0, y, width, y + 1)).getbbox():
            if not bands or y - bands[-1][1] > max(2, height * 0.04):
                bands.append([y, y + 1])
            else:
                bands[-1][1] = y + 1
    if height > 300 and len(bands) > 1:
        first, following = bands[0], bands[1]
        if (first[1] < height * 0.15 and first[1] - first[0] < height * 0.03
                and following[0] - first[1] > height * 0.04):
            top = first[1]
        previous, last = bands[-2], bands[-1]
        if (last[0] > height * 0.85 and last[1] - last[0] < height * 0.05
                and last[0] - previous[1] > height * 0.1):
            bottom = last[0]
    bounds = ink.crop((0, top, width, bottom)).getbbox()
    if bounds:
        left, upper, right, lower = bounds
        padding = 12
        return preview.crop((max(0, left-padding), max(top, top+upper-padding),
                             min(width, right+padding), min(bottom, top+lower+padding)))
    return preview


def retain_generator_details(run_dir: Path) -> None:
    process = run_dir / "process"
    for source in (process / "Cards").glob("*.dat"):
        if source.is_file() and not source.is_symlink():
            destination = run_dir / "cards" / "generated" / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    for source in sorted((process / "SubProcesses").glob("P*/matrix*.ps")):
        if source.is_symlink() or not source.resolve().is_relative_to(process.resolve()):
            continue
        destination = run_dir / "diagrams" / source.parent.name / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        renderer = shutil.which("gs")
        if renderer:
            try:
                result = subprocess.run(
                    [
                        renderer,
                        "-dSAFER",
                        "-dBATCH",
                        "-dNOPAUSE",
                        "-sDEVICE=pngalpha",
                        "-r100",
                        "-dLastPage=4",
                        f"-sOutputFile={destination.with_suffix('')}_%03d.png",
                        str(destination),
                    ],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                if result.returncode:
                    destination.with_suffix(".render.log").write_bytes(result.stderr)
            except (OSError, subprocess.TimeoutExpired) as error:
                destination.with_suffix(".render.log").write_text(str(error))


def render_generator_details(run_dir: Path) -> None:
    import streamlit as st

    with st.expander("Feynman diagrams", expanded=True):
        diagrams = sorted((run_dir / "diagrams").glob("*/*.ps"))
        if not diagrams:
            st.info("No retained diagrams for this run. New MadGraph runs save them automatically.")
        else:
            controls, preview_column = st.columns([1, 2.4], gap="large")
            with controls:
                selected = st.selectbox(
                    "Partonic subprocess",
                    diagrams,
                    format_func=lambda p: f"{p.parent.name} / {p.stem}",
                    key=f"diagrams_{run_dir.name}",
                )
                st.caption(
                    "MadGraph matrix-element diagrams, not a shower history. "
                    "Preview shows up to four pages; download contains all diagrams."
                )
                st.download_button(
                    "Download PS",
                    selected.read_bytes(),
                    file_name=f"{selected.parent.name}_{selected.name}",
                    mime="application/postscript",
                )
                previews = sorted(selected.parent.glob(f"{selected.stem}_*.png"))
                page = (
                    st.number_input(
                        "Diagram page",
                        min_value=1,
                        max_value=len(previews),
                        step=1,
                        key=f"diagram_page_{run_dir.name}_{selected.stem}_{selected.parent.name}",
                    )
                    if len(previews) > 1
                    else 1
                )
            with preview_column:
                if previews:
                    st.image(diagram_preview(previews[int(page) - 1]), width=500)
                else:
                    st.caption("Preview unavailable; download the native diagrams.")


def render_text_files(run_dir: Path, folder: str, label: str) -> None:
    import streamlit as st

    files = sorted(
        path
        for path in (run_dir / folder).rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.resolve().is_relative_to(run_dir.resolve())
    )
    if not files:
        st.caption(f"No retained {label.lower()} for this run.")
        return
    for path in files:
        relative = str(path.relative_to(run_dir / folder))
        with st.expander(relative, expanded=False):
            st.download_button("Download file", path.read_bytes(), file_name=path.name,
                               mime="text/plain", key=f"download_{folder}_{run_dir.name}_{relative}")
            text = path.read_text(errors="replace")
            st.code(text[-30000:], language="text")
            if len(text) > 30000:
                st.caption("Showing the last 30,000 characters; download includes the full file.")


def used_card_paths(run_dir: Path, manifest: dict) -> list[Path]:
    """Select active inputs for the supported pipeline, never bundled templates."""
    cards = run_dir / "cards"
    names = ["madgraph_process.mg5", "madevent_commands.txt",
             "generated/run_card.dat", "generated/param_card.dat"]
    if not (cards / "madgraph_process.mg5").is_file():
        names.append("generated/proc_card_mg5.dat")
    if manifest.get("config", {}).get("run_mode") == "full":
        names.append("generated/pythia8_card.dat")
        names.append("delphes_card.dat" if (cards / "delphes_card.dat").is_file()
                     else "generated/delphes_card.dat")
    return [cards / name for name in names if (cards / name).is_file()
            and not (cards / name).is_symlink()
            and (cards / name).resolve().is_relative_to(run_dir.resolve())]


def render_settings_files(run_dir: Path, manifest: dict) -> None:
    import streamlit as st

    files = [
        (
            "Saved run configuration (JSON)",
            f"{run_dir.name}-manifest.json",
            json.dumps(manifest, indent=2).encode(),
            "json",
            "application/json",
        )
    ]
    cards = run_dir / "cards"
    if not (cards / "generated" / "run_card.dat").exists():
        st.caption("This older run does not retain the generated MadGraph run/parameter cards. "
                   "Available command files and detector cards are listed below.")
    else:
        st.caption("Run inputs only; unused defaults and alternative detector templates are hidden.")
    for path in used_card_paths(run_dir, manifest):
        if (
            path.is_file()
            and not path.is_symlink()
            and path.resolve().is_relative_to(run_dir.resolve())
        ):
            files.append(
                (str(path.relative_to(cards)), path.name, path.read_bytes(), "text", "text/plain")
            )
    for label, filename, content, language, mime in files:
        with st.expander(label, expanded=False):
            st.download_button(
                "Download file",
                content,
                file_name=filename,
                mime=mime,
                key=f"settings_download_{run_dir.name}_{label}",
            )
            text = content.decode(errors="replace")
            st.code(text[:30000], language=language)
            if len(text) > 30000:
                st.caption("Preview truncated; download includes the complete file.")


def render_run_files(run_dir: Path, manifest: dict, analysis_path: Path) -> None:
    import streamlit as st

    with st.expander("Run files and details", expanded=False):
        events, settings, logs = st.tabs(["Event files", "Settings and cards", "Execution logs"])
        with events:
            choices = {"Analysis table (CSV)": (analysis_path, "text/csv")}
            for stage, label, mime in [
                ("matrix_element", "Generator events (LHE)", "application/gzip"),
                ("detector_root", "Detector events (ROOT)", "application/octet-stream"),
            ]:
                relative = manifest.get("stages", {}).get(stage)
                if relative:
                    path = (run_dir / relative).resolve()
                    if path.is_relative_to(run_dir.resolve()) and path.is_file():
                        choices[label] = (path, "text/plain" if path.suffix == ".lhe" else mime)
            descriptions = {
                "Analysis table (CSV)": "Derived analysis variables; not the complete event record.",
                "Generator events (LHE)": "Parton-level particles and generator weights, before showering.",
                "Detector events (ROOT)": "Retained Delphes objects for notebook analysis.",
            }
            for column, (label, (path, mime)) in zip(
                st.columns(len(choices)), choices.items(), strict=True
            ):
                with column:
                    st.download_button(
                        label,
                        path.read_bytes(),
                        file_name=path.name,
                        mime=mime,
                        key=f"download_{label}_{run_dir.name}",
                        width="stretch",
                    )
                    st.caption(descriptions[label])
        with settings:
            render_settings_files(run_dir, manifest)
        with logs:
            render_text_files(run_dir, "logs", "Execution logs")
