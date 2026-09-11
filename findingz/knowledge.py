from __future__ import annotations

import re
from pathlib import Path


def default_knowledge_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "course_knowledge"


def search_course_notes(
    query: str, limit: int = 3, root: Path | None = None
) -> list[dict[str, str]]:
    directory = root or default_knowledge_dir()
    query_terms = {term.lower() for term in re.findall(r"[A-Za-z0-9]+", query) if len(term) > 2}
    ranked: list[tuple[int, Path, str]] = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for block in (part.strip() for part in text.split("\n\n") if part.strip()):
            terms = set(re.findall(r"[A-Za-z0-9]+", block.lower()))
            score = len(query_terms & terms)
            if score:
                ranked.append((score, path, block))
    ranked.sort(key=lambda item: (-item[0], item[1].name))
    return [{"source": item[1].name, "text": item[2]} for item in ranked[:limit]]
