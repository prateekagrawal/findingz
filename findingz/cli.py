"""Launch the same installed UI in local Docker or CIT's hep environment."""
import sys
from pathlib import Path


def main():
    from streamlit.web import cli

    sys.argv = ["streamlit", "run", str(Path(__file__).with_name("ui.py")), *sys.argv[1:]]
    raise SystemExit(cli.main())
