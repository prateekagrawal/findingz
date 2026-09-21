"""Save editable analysis notebooks without requiring a running notebook server."""
import json
import os
import re
from pprint import pformat
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


def notebook_directory():
    return Path(os.environ.get("FINDINGZ_NOTEBOOK_DIR", str(Path.home() / "findingz-notebooks"))).expanduser().resolve()


def template_path():
    configured = os.environ.get("FINDINGZ_NOTEBOOK_TEMPLATE")
    return Path(configured).expanduser() if configured else Path(__file__).parent / "resources/notebooks/analysis_template.ipynb"


def notebook_url(path):
    # Prefix maps exactly to NOTEBOOK_DIR in the notebook server's file browser.
    prefix = os.environ.get("FINDINGZ_NOTEBOOK_URL_PREFIX", "").strip()
    return prefix.rstrip("/") + "/" + quote(Path(path).name) if prefix else None


def save_notebook(name, snapshot=None):
    template = template_path()
    document = json.loads(template.read_text())
    kernel = os.environ.get("FINDINGZ_NOTEBOOK_KERNEL", "").strip()
    if kernel:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", kernel):
            raise ValueError("FINDINGZ_NOTEBOOK_KERNEL must be an installed kernel name")
        document.setdefault("metadata", {})["kernelspec"] = {
            "name": kernel, "language": "python",
            "display_name": {"findingz": "Python (Finding Z)", "hep": "Python (hep)"}.get(kernel, kernel),
        }
    cells = document.get("cells", [])
    slots = [cell for cell in cells if "findingz-settings" in cell.get("metadata", {}).get("tags", [])]
    if document.get("nbformat") != 4 or len(slots) != 1 or slots[0].get("cell_type") != "code":
        raise ValueError("Template must be nbformat 4 with exactly one code cell tagged findingz-settings.")
    settings = snapshot or {"plot": None, "count": None}
    normalized = json.loads(json.dumps(settings, allow_nan=False))
    # New templates expose literal student choices, independent of provenance.
    plot = normalized.get("plot") or {}
    count = normalized.get("count") or {}
    if count and count.get("mode") != "hypothesis_comparison":
        raise ValueError("This saved count uses legacy additive roles. Choose null and alternative predictions again before exporting.")
    if count and document.get("metadata", {}).get("findingz_count_mode") != "hypothesis_comparison":
        raise ValueError("The course notebook template needs updating for null/alternative comparison. No notebook was saved.")
    choices = {
        "findingz-plot-choices": dict(sample_ids=plot.get("samples", []),
            observable=plot.get("observable", "mll"),
            shape_only=not plot.get("expected_yields", False),
            luminosity_fb=plot.get("luminosity_fb", 1.0)),
        "findingz-cut-choices": dict(cuts=plot.get("windows", {}),
            channels=plot.get("channels", None)),
        "findingz-count-choices": dict(null_id=count.get("null"),
            alternative_id=count.get("alternative"),
            count_cuts=count.get("windows", {}), count_channels=count.get("channels"),
            count_luminosity_fb=count.get("luminosity_fb", 1.0),
            null_uncertainty=count.get("null_uncertainty_fraction", 0.0)),
    }
    for cell in cells:
        for tag, values in choices.items():
            if tag in cell.get("metadata", {}).get("tags", []):
                cell["source"] = "\n".join(
                    f"{key} = {pformat(value, width=88, sort_dicts=False)}"
                    for key, value in values.items()) + "\n"
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    document.setdefault("metadata", {})["findingz"] = {
        "template": str(template), "created_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "current" if snapshot is not None else "blank",
    }
    entered = name.strip()
    if entered.lower().endswith(".ipynb"):
        entered = entered[:-6]
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", entered).strip("-")[:80] or "analysis"
    directory = notebook_directory()
    directory.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against concurrent requests using the same name.
    for number in range(1, 10001):
        suffix = "" if number == 1 else f"-{number}"
        path = directory / f"{stem}{suffix}.ipynb"
        settings_path = path.with_suffix(".settings.json")
        if settings_path.exists():
            continue
        try:
            stream = path.open("x", encoding="utf-8")
        except FileExistsError:
            continue
        with stream:
            with settings_path.open("x", encoding="utf-8") as settings_stream:
                json.dump(normalized, settings_stream, indent=2, ensure_ascii=False)
                settings_stream.write("\n")
            slots[0]["source"] = (
                "from findingz.notebook_analysis import load_analysis\n"
                f"analysis = load_analysis({settings_path.name!r})\n"
                "saved_plot = analysis.get('plot') or {}\n"
                "saved_count = analysis.get('count') or {}\n"
            )
            json.dump(document, stream, indent=1, ensure_ascii=False)
            stream.write("\n")
        return path
    raise ValueError("Too many notebooks with this name; choose another name.")
