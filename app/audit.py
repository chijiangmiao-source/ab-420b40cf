"""Audit assembly: turn a validated request into the audit report.

The dominator tree is computed once over the subgraph reachable from the
root; dominated-terminal counts are then accumulated in a single reverse
dfs-order pass over that tree.  No per-node reachability re-runs, no
recursion, no graph libraries.
"""

from __future__ import annotations

from typing import Any

from app.dominators import compute_immediate_dominators


def run_audit(
    nodes: list[str],
    root: str,
    terminals: list[str],
    edges: list[tuple[str, str]],
) -> dict[str, Any]:
    index = {name: i for i, name in enumerate(nodes)}
    n = len(nodes)

    succ: list[list[int]] = [[] for _ in range(n)]
    pred: list[list[int]] = [[] for _ in range(n)]
    for src, dst in edges:
        iu = index[src]
        iv = index[dst]
        succ[iu].append(iv)
        pred[iv].append(iu)

    dom = compute_immediate_dominators(n, succ, pred, index[root])

    is_terminal = bytearray(n)
    terminal_ids: list[int] = []
    for name in terminals:
        i = index[name]
        is_terminal[i] = 1
        terminal_ids.append(i)

    # Terminals dominated by a node are exactly the terminals in its
    # dominator-tree subtree.  A dominator always has a smaller dfs number
    # than the nodes it dominates, so one reverse-order pass accumulates
    # every subtree count.
    counts = [0] * n
    for i in terminal_ids:
        counts[i] = 1
    for k in range(dom.size, 1, -1):
        w = dom.vertex[k]
        counts[dom.idom[w]] += counts[w]

    unreachable_terminals = sorted(nodes[i] for i in terminal_ids if dom.semi[i] == 0)

    idom_entries: list[tuple[str, str]] = []
    critical: list[tuple[str, int]] = []
    for k in range(2, dom.size + 1):  # reachable nodes, root excluded
        w = dom.vertex[k]
        idom_entries.append((nodes[w], nodes[dom.idom[w]]))
        if not is_terminal[w] and counts[w] > 0:
            critical.append((nodes[w], counts[w]))
    idom_entries.sort(key=lambda entry: entry[0])
    critical.sort(key=lambda entry: entry[0])

    return {
        "unreachable_terminals": unreachable_terminals,
        "immediate_dominators": [
            {"node": node, "idom": idom} for node, idom in idom_entries
        ],
        "critical_relays": [
            {"node": node, "dominated_terminals": count} for node, count in critical
        ],
    }
