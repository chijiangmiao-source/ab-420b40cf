"""Application build check: byte-compile all sources and import the ASGI app.

Exits 0 when the application imports cleanly and exposes the expected
routes, 1 otherwise.
"""

from __future__ import annotations

import compileall
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)


def main() -> int:
    ok = True
    for directory in ("app", "scripts", "tests"):
        if not compileall.compile_dir(directory, quiet=1, workers=1):
            print(f"build check: byte-compilation failed for {directory}/")
            ok = False
    if not ok:
        return 1

    from app.main import app

    schema = app.openapi()
    paths = schema.get("paths", {})
    for expected in ("/api/audit", "/health"):
        if expected not in paths:
            print(f"build check: missing route {expected}")
            return 1
    print("build check: sources compile, app imports, routes present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
