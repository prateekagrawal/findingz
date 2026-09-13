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
    cells = document.get("cells", [])
    slots = [cell for cell in cells if "findingz-settings" in cell.get("metadata", {}).get("tags", [])]
    if document.get("nbformat") != 4 or len(slots) != 1 or slots[0].get("cell_type") != "code":
        raise ValueError("Template must be nbformat 4 with exactly one code cell tagged findingz-settings.")
    settings = snapshot or {"plot": None, "count": None}
    # Keep the full snapshot readable and executable, without a giant escaped JSON line.
    normalized = json.loads(json.dumps(settings, allow_nan=False))
    slots[0]["source"] = "analysis = " + pformat(normalized, width=88, sort_dicts=False) + "\n"
    for cell in cells:
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
        try:
            stream = path.open("x", encoding="utf-8")
        except FileExistsError:
            continue
        with stream:
            json.dump(document, stream, indent=1, ensure_ascii=False)
            stream.write("\n")
        return path
    raise ValueError("Too many notebooks with this name; choose another name.")
