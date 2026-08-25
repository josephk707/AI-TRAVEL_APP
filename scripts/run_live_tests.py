"""
Runs the live-database test suites with backend/.env loaded into the child
process's environment via python-dotenv (a real parser) — never via shell
sourcing, which previously mis-parsed special characters and leaked
credentials into a terminal transcript (see docs/PHASE_STATUS.md Phase 2
"known limitations"). No secret is printed by this script; pytest's own
output only ever contains assertion messages, which this project's test
files are written to keep free of secret values.

Usage:
    python scripts/run_live_tests.py [pytest args...]
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
BACKEND_ENV = BACKEND_DIR / ".env"


def main() -> int:
    load_dotenv(dotenv_path=BACKEND_ENV)

    pytest_args = sys.argv[1:] or [
        "tests/test_live_database.py",
        "tests/test_rls_security.py",
        "-v",
    ]

    result = subprocess.run(
        [str(BACKEND_DIR / ".venv" / "Scripts" / "python.exe"), "-m", "pytest", *pytest_args],
        cwd=str(BACKEND_DIR),
        env=os.environ,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
