"""Launch Streamlit with this project's explicit .env settings."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values


def build_environment(root: Path, inherited: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if inherited is None else inherited)
    environment.update(
        {key: value for key, value in dotenv_values(root / ".env").items() if value is not None}
    )
    environment["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    return environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8503)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(root / "streamlit_app.py"),
        "--server.address=localhost",
        f"--server.port={args.port}",
        "--server.headless=true",
    ]
    return subprocess.run(command, cwd=root, env=build_environment(root)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
