"""Launch the member 6 web UI while the conversational CLI backend is pending."""

import sys
from pathlib import Path


def main() -> None:
    from streamlit.web import cli

    entrypoint = Path(__file__).resolve().parents[1] / "web" / "app.py"
    sys.argv = [
        "streamlit",
        "run",
        str(entrypoint),
        "--server.address=localhost",
        "--browser.gatherUsageStats=false",
        *sys.argv[1:],
    ]
    raise SystemExit(cli.main())
