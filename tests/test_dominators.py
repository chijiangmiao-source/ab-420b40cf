"""Unit tests for the dominator core, cross-checked against brute force."""

from __future__ import annotations

import random

from app.audit import run_audit
from app.dominators import compute_immediate_dominators


def _adjacency(n: int, edges: list[tuple[int, int]]):
    succ: list[list[int]] = [[] for _ in range(n)]
    pred: list[list[int]] = [[] for _ in range(n)]
    for u, v in edges:
        succ[u].append(v)
        pred[v].append(u)
    return succ, pred


def _brute_force_dominators(n: int, edges: list[tuple[int, int]], root: int):
    """Naive iterative dataflow dominator sets (test oracle, not the service)."""
    succ, pred = _adjacency(n, edges)
    reach = [False] * n
    reach[root] = True
    stack = [root]
    while stack:
        v = stack.pop()
        for w in succ[v]:
            if not reach[w]:
                reach[w] = True
                stack.append(w)
    universe = {v for v in range(n) if reach[v]}
    dom = [set() for _ in range(n)]
    for v in universe:
        dom[v] = {root} if v == root else set(universe)
    changed = True
    while changed:
        changed = False
        for v in universe:
            if v == root:
                continue
            preds = [dom[p] for p in pred[v] if reach[p]]
            new = (set.intersection(*preds) if preds else set()) | {v}
            if new != dom[v]:
                dom[v] = new
                changed = True
    return reach, dom


def _brute_force_idom(n: int, edges: list[tuple[int, int]], root: int) -> dict[int, int]:
    reach, dom = _brute_force_dominators(n, edges, root)
    idom: dict[int, int] = {}
    for v in range(n):
        if not reach[v] or v == root:
            continue
        strict = dom[v] - {v}
        # Strict dominators form a chain; the immediate dominator is the one
        # dominated by all the others, i.e. the one with the largest dom set.
        idom[v] = max(strict, key=lambda d: len(dom[d]))
    return idom


def test_diamond_bypass_has_no_critical_relay():
    result = run_audit(
        nodes=["R", "A", "B", "T"],
        root="R",
        terminals=["T"],
        edges=[("R", "A"), ("R", "B"), ("A", "T"), ("B", "T")],
    )
    assert result["unreachable_terminals"] == []
    assert result["immediate_dominators"] == [
        {"node": "A", "idom": "R"},
        {"node": "B", "idom": "R"},
        {"node": "T", "idom": "R"},
    ]
    assert result["critical_relays"] == []


def test_series_relays_are_critical():
    result = run_audit(
        nodes=["R", "A", "B", "T"],
        root="R",
        terminals=["T"],
        edges=[("R", "A"), ("A", "B"), ("B", "T")],
    )
    assert result["immediate_dominators"] == [
        {"node": "A", "idom": "R"},
        {"node": "B", "idom": "A"},
        {"node": "T", "idom": "B"},
    ]
    assert result["critical_relays"] == [
        {"node": "A", "dominated_terminals": 1},
        {"node": "B", "dominated_terminals": 1},
    ]


def test_parallel_edges_are_tolerated():
    result = run_audit(
        nodes=["R", "A", "T"],
        root="R",
        terminals=["T"],
        edges=[("R", "A"), ("R", "A"), ("A", "T"), ("A", "T"), ("A", "T")],
    )
    assert result["immediate_dominators"] == [
        {"node": "A", "idom": "R"},
        {"node": "T", "idom": "A"},
    ]
    assert result["critical_relays"] == [{"node": "A", "dominated_terminals": 1}]


def test_unreachable_terminal_is_reported_and_not_counted():
    result = run_audit(
        nodes=["R", "A", "T1", "T2"],
        root="R",
        terminals=["T1", "T2"],
        edges=[("R", "A"), ("A", "T1")],
    )
    assert result["unreachable_terminals"] == ["T2"]
    assert result["immediate_dominators"] == [
        {"node": "A", "idom": "R"},
        {"node": "T1", "idom": "A"},
    ]
    assert result["critical_relays"] == [{"node": "A", "dominated_terminals": 1}]


def test_shared_relay_counts_all_dominated_terminals():
    result = run_audit(
        nodes=["R", "A", "B", "T1", "T2", "T3"],
        root="R",
        terminals=["T1", "T2", "T3"],
        edges=[
            ("R", "A"),
            ("A", "B"),
            ("B", "T1"),
            ("B", "T2"),
            ("A", "T3"),
        ],
    )
    assert result["critical_relays"] == [
        {"node": "A", "dominated_terminals": 3},
        {"node": "B", "dominated_terminals": 2},
    ]


def test_idom_matches_brute_force_on_random_graphs():
    rng = random.Random(20260924)
    for _ in range(300):
        n = rng.randint(2, 40)
        edges = [
            (u, v)
            for u, v in ((rng.randrange(n), rng.randrange(n)) for _ in range(rng.randint(0, 120)))
            if u != v
        ]
        root = rng.randrange(n)
        succ, pred = _adjacency(n, edges)
        res = compute_immediate_dominators(n, succ, pred, root)
        reach, _ = _brute_force_dominators(n, edges, root)
        expected = _brute_force_idom(n, edges, root)
        for v in range(n):
            if not reach[v]:
                assert res.semi[v] == 0
                assert res.idom[v] == -1
            elif v == root:
                assert res.idom[v] == -1
            else:
                assert res.idom[v] == expected[v]


def test_critical_counts_match_brute_force_on_random_graphs():
    rng = random.Random(777)
    for _ in range(200):
        n = rng.randint(2, 30)
        names = [f"n{i}" for i in range(n)]
        root = "n0"
        terminals = rng.sample(names, rng.randint(1, min(6, n)))
        terminal_set = set(terminals)
        edges = [
            (names[u], names[v])
            for u, v in ((rng.randrange(n), rng.randrange(n)) for _ in range(rng.randint(0, 80)))
            if u != v and names[u] not in terminal_set
        ]
        result = run_audit(names, root, terminals, edges)

        index = {name: i for i, name in enumerate(names)}
        int_edges = [(index[u], index[v]) for u, v in edges]
        reach, dom = _brute_force_dominators(n, int_edges, index[root])
        t_idx = {index[t] for t in terminals}

        expected_critical = {}
        for w in range(n):
            if w == index[root] or w in t_idx or not reach[w]:
                continue
            count = sum(1 for t in t_idx if reach[t] and w in dom[t])
            if count > 0:
                expected_critical[names[w]] = count
        got_critical = {e["node"]: e["dominated_terminals"] for e in result["critical_relays"]}
        assert got_critical == expected_critical

        expected_unreachable = sorted(t for t in terminals if not reach[index[t]])
        assert result["unreachable_terminals"] == expected_unreachable

        expected_idom = _brute_force_idom(n, int_edges, index[root])
        got_idom = {e["node"]: e["idom"] for e in result["immediate_dominators"]}
        assert got_idom == {names[v]: names[d] for v, d in expected_idom.items()}


def test_deep_chain_does_not_recurse():
    # A 200k-deep chain would instantly kill any recursive traversal.
    n = 200_000
    edges = [(i, i + 1) for i in range(n - 1)]
    succ, pred = _adjacency(n, edges)
    res = compute_immediate_dominators(n, succ, pred, 0)
    assert res.size == n
    for v in range(1, n):
        assert res.idom[v] == v - 1


def test_large_sparse_graph_performance_shape():
    rng = random.Random(42)
    n = 200_000
    edges: list[tuple[int, int]] = []
    for v in range(1, n):
        edges.append((rng.randrange(v), v))  # guarantee reachability
        edges.append((rng.randrange(v), v))  # parallel edge
    edges.append((0, 0 + 1))  # duplicate-ish extra
    succ, pred = _adjacency(n, edges)
    res = compute_immediate_dominators(n, succ, pred, 0)
    assert res.size == n
