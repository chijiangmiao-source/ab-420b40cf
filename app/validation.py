"""Semantic request validation beyond what the schema can express.

Every problem is reported with a JSON-pointer-like ``loc`` path so the
caller can locate it, and the audit is refused as a whole (never partially
returned) whenever at least one problem exists.
"""

from __future__ import annotations

from app.schemas import AuditRequest


class AuditInputError(Exception):
    """Raised when a syntactically valid request fails semantic checks."""

    def __init__(self, errors: list[dict]) -> None:
        super().__init__(f"{len(errors)} input error(s)")
        self.errors = errors


def _err(path: list, msg: str, err_type: str) -> dict:
    return {"loc": ["body", *path], "msg": msg, "type": err_type}


def collect_input_errors(req: AuditRequest) -> list[dict]:
    errors: list[dict] = []

    node_set: set[str] = set()
    for i, name in enumerate(req.nodes):
        if name in node_set:
            errors.append(
                _err(["nodes", i], f"duplicate node identifier {name!r}", "duplicate_identifier")
            )
        else:
            node_set.add(name)

    if req.root not in node_set:
        errors.append(
            _err(["root"], f"dangling reference: root {req.root!r} is not a declared node",
                 "dangling_reference")
        )

    terminal_set: set[str] = set()
    for i, name in enumerate(req.terminals):
        if name in terminal_set:
            errors.append(
                _err(["terminals", i], f"duplicate terminal identifier {name!r}",
                     "duplicate_identifier")
            )
            continue
        terminal_set.add(name)
        if name not in node_set:
            errors.append(
                _err(["terminals", i],
                     f"dangling reference: terminal {name!r} is not a declared node",
                     "dangling_reference")
            )

    for i, (src, dst) in enumerate(req.edges):
        if src not in node_set:
            errors.append(
                _err(["edges", i, 0], f"dangling reference: unknown node {src!r}",
                     "dangling_reference")
            )
        if dst not in node_set:
            errors.append(
                _err(["edges", i, 1], f"dangling reference: unknown node {dst!r}",
                     "dangling_reference")
            )
        if src == dst:
            errors.append(
                _err(["edges", i], f"self-loop on node {src!r} is forbidden", "self_loop")
            )
        if src in terminal_set:
            errors.append(
                _err(["edges", i, 0],
                     f"protected terminal {src!r} must not have outgoing edges",
                     "terminal_outgoing_edge")
            )

    return errors
