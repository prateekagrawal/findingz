"""Read-only, bounded progress details for a running generator."""
import re
import time
from pathlib import Path


def latest_log(run_dir: Path) -> tuple[str, str, float] | None:
    logs = [p for p in (run_dir / "logs").glob("*.log")
            if p.is_file() and not p.is_symlink()]
    if not logs:
        return None
    path = max(logs, key=lambda p: p.stat().st_mtime)
    stat = path.stat()
    with path.open("rb") as source:
        offset = max(0, stat.st_size - 8192)
        source.seek(offset)
        text = source.read(8192).decode(errors="replace")
    if offset:
        text = text.partition("\n")[2]
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    return path.name, "\n".join(text.splitlines()[-14:]), max(0, time.time() - stat.st_mtime)


def render_progress_details(job: dict) -> None:
    import streamlit as st

    now = time.monotonic()
    elapsed = max(0, int(now - job.get("started_at", now)))
    stage_time = max(0, int(now - job.get("stage_started_at", now)))
    st.caption(f"Elapsed {elapsed // 60}m {elapsed % 60:02d}s · "
               f"Current stage {stage_time // 60}m {stage_time % 60:02d}s")
    if job.get("summary"):
        st.write(job["summary"])
    st.caption("Stages are not equal in duration. Integration can take several minutes; "
               "no reliable completion-time estimate is available. Analysis remains usable.")
    if not job.get("run_dir"):
        return
    try:
        log = latest_log(Path(job["run_dir"]))
        if log:
            name, tail, age = log
            st.caption(f"Latest generator output · {name} · updated {int(age)}s ago")
            st.code(tail or "Waiting for generator output…", language="text")
            if age > 30:
                st.caption("The log may be buffered. A quiet log alone does not mean the run is stuck.")
        else:
            st.caption("Waiting for the generator to create its log…")
    except OSError:
        st.caption("Log temporarily unavailable; the generator is still being monitored.")
