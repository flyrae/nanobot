"""End-to-end demo for Windows computer-use skill.

Default is dry-run (no UI actions). Use --execute to run real actions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / ".." / "nanobot" / "skills" / "windows-computer-use" / "scripts" / "computer_use.py"
SCRIPT = SCRIPT.resolve()


def _run(command: list[str], execute: bool) -> None:
    if not execute:
        print("DRY_RUN:", " ".join(command))
        return
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Windows computer-use E2E demo")
    parser.add_argument("--execute", action="store_true", help="Run real UI actions")
    parser.add_argument("--app", default="notepad", help="App to open")
    parser.add_argument("--title", default="Notepad", help="Window title substring")
    parser.add_argument("--text", default="Hello from nanobot!", help="Text to type")
    args = parser.parse_args()

    python = sys.executable

    steps = [
        [python, str(SCRIPT), "open_app", "--app", args.app],
        [python, str(SCRIPT), "focus_window", "--title", args.title],
        [python, str(SCRIPT), "type_text", "--text", args.text],
        [python, str(SCRIPT), "screenshot", "--path", str(Path.cwd() / "e2e_demo.png")],
        [python, str(SCRIPT), "point_confirm", "--x", "100", "--y", "100", "--hint", "top-left sanity check"],
    ]

    for cmd in steps:
        _run(cmd, args.execute)

    if not args.execute:
        print(json.dumps({"note": "Use --execute to perform real UI actions."}, ensure_ascii=False))


if __name__ == "__main__":
    main()
