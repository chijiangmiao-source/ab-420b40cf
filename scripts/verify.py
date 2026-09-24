"""One-shot verification runner: unit tests, build check, HTTP smoke.

Runs every stage, prints a per-stage verdict, and exits 0 only if all
stages succeeded — the container exit code is the final conclusion.
"""

from __future__ import annotations

import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STAGES = [
    ("unit tests", [sys.executable, "-m", "pytest", "tests", "-q"]),
    ("build check", [sys.executable, "scripts/build_check.py"]),
    ("http smoke", [sys.executable, "scripts/smoke.py"]),
]


def main() -> int:
    os.chdir(REPO_ROOT)
    failures: list[str] = []
    for name, cmd in STAGES:
        print(f"\n===== verify stage: {name} =====", flush=True)
        returncode = subprocess.run(cmd, cwd=REPO_ROOT).returncode
        verdict = "ok" if returncode == 0 else "FAILED"
        print(f"===== verify stage: {name} -> {verdict} =====", flush=True)
        if returncode != 0:
            failures.append(name)

    print()
    if failures:
        print(f"VERIFY FAILED: {', '.join(failures)}")
        return 1
    print("VERIFY OK: all stages passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
