"""Instructor-approved UFO directories; never import Python while inspecting them."""
import hashlib
from pathlib import Path


def ufo_digest(directory: str | Path) -> str:
    root = Path(directory).resolve()
    for name in ("__init__.py", "particles.py", "parameters.py", "vertices.py", "couplings.py", "object_library.py"):
        if not (root / name).is_file():
            raise ValueError(f"Incomplete UFO model: missing {root / name}")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError(f"UFO models must not contain symlinks: {path}")
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode() + b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()
