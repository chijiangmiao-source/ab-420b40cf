"""HTTP smoke tests against a running auditor service.

Covers the mandated scenarios: diamond bypass, series critical points,
parallel edges and unreachable terminals, plus health and error handling.
Exits 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import os
import sys
import time

import httpx

BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")

FAILED = "\033[31mFAIL\033[0m" if sys.stdout.isatty() else "FAIL"
PASSED = "\033[32mPASS\033[0m" if sys.stdout.isatty() else "PASS"


def check(name: str, condition: bool, detail: str = "") -> bool:
    print(f"[{PASSED if condition else FAILED}] {name}")
    if not condition and detail:
        print(f"       {detail}")
    return condition


def wait_for_health(client: httpx.Client, attempts: int = 60) -> bool:
    for _ in range(attempts):
        try:
            if client.get("/health").status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def main() -> int:
    ok = True
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        if not wait_for_health(client):
            print(f"[{FAILED}] service at {BASE_URL} never became healthy")
            return 1
        ok &= check("health endpoint reports availability", True)

        # 1. Diamond bypass: neither branch relay is a single point of failure.
        r = client.post(
            "/api/audit",
            json={
                "root": "R",
                "nodes": ["R", "A", "B", "T"],
                "terminals": ["T"],
                "edges": [["R", "A"], ["R", "B"], ["A", "T"], ["B", "T"]],
            },
        )
        body = r.json() if r.status_code == 200 else {}
        ok &= check(
            "diamond bypass: no relay is critical, join dominated by root",
            r.status_code == 200
            and body.get("critical_relays") == []
            and body.get("unreachable_terminals") == []
            and body.get("immediate_dominators")
            == [
                {"node": "A", "idom": "R"},
                {"node": "B", "idom": "R"},
                {"node": "T", "idom": "R"},
            ],
            f"status={r.status_code} body={r.text[:400]}",
        )

        # 2. Series chain: every intermediate relay is a critical point.
        r = client.post(
            "/api/audit",
            json={
                "root": "R",
                "nodes": ["R", "A", "B", "T"],
                "terminals": ["T"],
                "edges": [["R", "A"], ["A", "B"], ["B", "T"]],
            },
        )
        body = r.json() if r.status_code == 200 else {}
        ok &= check(
            "series chain: A and B are critical relays",
            r.status_code == 200
            and body.get("critical_relays")
            == [
                {"node": "A", "dominated_terminals": 1},
                {"node": "B", "dominated_terminals": 1},
            ]
            and body.get("immediate_dominators")
            == [
                {"node": "A", "idom": "R"},
                {"node": "B", "idom": "A"},
                {"node": "T", "idom": "B"},
            ],
            f"status={r.status_code} body={r.text[:400]}",
        )

        # 3. Parallel edges are accepted and do not change the dominators.
        r = client.post(
            "/api/audit",
            json={
                "root": "R",
                "nodes": ["R", "A", "T"],
                "terminals": ["T"],
                "edges": [["R", "A"], ["R", "A"], ["A", "T"], ["A", "T"]],
            },
        )
        body = r.json() if r.status_code == 200 else {}
        ok &= check(
            "parallel edges: tolerated, single critical relay",
            r.status_code == 200
            and body.get("critical_relays") == [{"node": "A", "dominated_terminals": 1}]
            and body.get("immediate_dominators")
            == [
                {"node": "A", "idom": "R"},
                {"node": "T", "idom": "A"},
            ],
            f"status={r.status_code} body={r.text[:400]}",
        )

        # 4. Unreachable terminals are listed and excluded from counts.
        r = client.post(
            "/api/audit",
            json={
                "root": "R",
                "nodes": ["R", "A", "T1", "T2"],
                "terminals": ["T1", "T2"],
                "edges": [["R", "A"], ["A", "T1"]],
            },
        )
        body = r.json() if r.status_code == 200 else {}
        ok &= check(
            "unreachable terminal: reported, not counted",
            r.status_code == 200
            and body.get("unreachable_terminals") == ["T2"]
            and body.get("critical_relays") == [{"node": "A", "dominated_terminals": 1}],
            f"status={r.status_code} body={r.text[:400]}",
        )

        # 5. Invalid input: locatable errors, no partial audit.
        r = client.post(
            "/api/audit",
            json={
                "root": "R",
                "nodes": ["R", "A", "A"],
                "terminals": ["A"],
                "edges": [["R", "GHOST"], ["A", "A"]],
            },
        )
        body = r.json()
        detail = body.get("detail", [])
        ok &= check(
            "invalid input: 422 with locatable errors and no partial audit",
            r.status_code == 422
            and any(e.get("loc") == ["body", "nodes", 2] for e in detail)
            and any(e.get("loc") == ["body", "edges", 0, 1] for e in detail)
            and any(e.get("type") == "self_loop" for e in detail)
            and "immediate_dominators" not in body
            and "critical_relays" not in body,
            f"status={r.status_code} body={r.text[:400]}",
        )

        # 6. Terminal with an outgoing edge is rejected.
        r = client.post(
            "/api/audit",
            json={
                "root": "R",
                "nodes": ["R", "A", "T"],
                "terminals": ["T"],
                "edges": [["R", "T"], ["T", "A"]],
            },
        )
        ok &= check(
            "terminal with outgoing edge: 422",
            r.status_code == 422
            and any(
                e.get("type") == "terminal_outgoing_edge" for e in r.json().get("detail", [])
            ),
            f"status={r.status_code} body={r.text[:400]}",
        )

    print("smoke: " + ("all checks passed" if ok else "FAILURES DETECTED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
