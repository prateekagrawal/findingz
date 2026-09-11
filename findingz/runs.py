from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

_RUN_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class SavedRun:
    run_id: str
    label: str
    run_type: str
    generated_events: int | None
    created_at: str
    analysis_path: Path
    manifest_path: Path

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["analysis_path"] = str(self.analysis_path)
        payload["manifest_path"] = str(self.manifest_path)
        return payload

    @property
    def menu_label(self) -> str:
        event_text = f"{self.generated_events:,} events" if self.generated_events else "event count unknown"
        return f"{self.label} — {self.run_type}, {event_text} [{self.run_id}]"


def _run_type(manifest: dict[str, object], config: dict[str, object]) -> str:
    if "pipeline" not in manifest:
        return "Fast pedagogical"
    return "Full HEP pipeline" if config.get("run_mode") == "full" else "MadGraph only"


def list_saved_runs(run_root: Path | str) -> list[SavedRun]:
    """Discover complete analysis checkpoints without relying on browser state."""
    root = Path(run_root).resolve()
    if not root.exists():
        return []
    found: list[SavedRun] = []
    for manifest_path in root.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("status") not in {None, "complete"}:
                continue
            run_id = str(manifest.get("run_id", manifest_path.parent.name))
            if not _RUN_ID.fullmatch(run_id) or run_id != manifest_path.parent.name:
                continue
            stages = manifest.get("stages")
            if not isinstance(stages, dict) or not isinstance(stages.get("analysis"), str):
                continue
            run_dir = manifest_path.parent.resolve()
            analysis_path = (run_dir / stages["analysis"]).resolve()
            if not analysis_path.is_relative_to(run_dir) or not analysis_path.is_file():
                continue
            config = manifest.get("config")
            config = config if isinstance(config, dict) else {}
            timestamp = manifest.get("created_at")
            if not isinstance(timestamp, str):
                timestamp = datetime.fromtimestamp(manifest_path.stat().st_mtime, tz=UTC).isoformat()
            label = manifest.get("label")
            label = str(label) if isinstance(label, str) and label.strip() else run_id
            generated = manifest.get("generated_events")
            found.append(
                SavedRun(
                    run_id=run_id,
                    label=label,
                    run_type=_run_type(manifest, config),
                    generated_events=int(generated) if isinstance(generated, int | float) else None,
                    created_at=timestamp,
                    analysis_path=analysis_path,
                    manifest_path=manifest_path.resolve(),
                )
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return sorted(found, key=lambda item: (item.created_at, item.run_id), reverse=True)


def saved_run(run_id: str, run_root: Path | str) -> SavedRun:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id may contain letters, digits, underscores, and hyphens only")
    match = next((item for item in list_saved_runs(run_root) if item.run_id == run_id), None)
    if match is None:
        raise FileNotFoundError(f"No complete saved run named {run_id!r}")
    return match
