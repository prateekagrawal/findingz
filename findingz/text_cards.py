"""Optional course-provided shower and detector card text."""
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict


class TextCardOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str | None = None
    editable: bool = False


def validate_card_text(text: str) -> str:
    if not text.strip() or "\0" in text or len(text.encode()) > 1_000_000:
        raise ValueError("Cards must be nonempty text files smaller than 1 MB, without NUL bytes")
    return text


def validate_shower_card(text: str) -> str:
    validate_card_text(text)
    settings = {}
    for line in text.splitlines():
        active = re.split(r"[!#]", line, maxsplit=1)[0]
        if "=" in active:
            name, value = active.split("=", 1)
            settings[name.strip().lower()] = value.strip().lower()
    if settings.get("main:numberofevents", "-1") != "-1":
        raise ValueError("Keep Main:numberOfEvents = -1 to shower all generated events; use the event-count control")
    if settings.get("hepmcoutput:file", "hepmc.gz") not in {"hepmc", "hepmc.gz"}:
        raise ValueError("Keep HEPMCoutput:file = hepmc or hepmc.gz so FindingZ can collect the shower output")
    return text


def shower_template(mg5_executable: Path | None) -> Path:
    if mg5_executable is None:
        raise ValueError("MadGraph is unavailable; supply a course shower card to edit it here")
    root = mg5_executable.resolve().parent.parent
    path = root / "Template/LO/Cards/pythia8_card_default.dat"
    if not path.is_file():
        raise ValueError("Pythia template not found; supply a course shower card")
    return path
