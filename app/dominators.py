"""Iterative Lengauer-Tarjan immediate dominator computation.

The graph is represented with integer node ids (0..n-1) and successor /
predecessor adjacency lists.  The implementation is fully iterative so that
arbitrarily deep graphs never hit the interpreter recursion limit, and it uses
no graph-algorithm library.
"""

from __future__ import annotations

from typing import NamedTuple


class DomResult(NamedTuple):
    idom: list[int]  # idom[v]: immediate dominator of v; -1 for root and unreachable nodes
    semi: list[int]  # semi[v] != 0 iff v is reachable from the root
    vertex: list[int]  # vertex[k]: node whose dfs number is k (1-based)
    size: int  # number of nodes reachable from the root


def compute_immediate_dominators(
    n: int,
    succ: list[list[int]],
    pred: list[list[int]],
    root: int,
) -> DomResult:
    """Return the immediate dominator of every node reachable from ``root``.

    Runs the classical four-step Lengauer-Tarjan algorithm in O(E * a(V))
    time with path compression, entirely without recursion.
    """
    semi = [0] * n
    vertex = [0] * (n + 1)
    parent = [-1] * n
    label = list(range(n))
    ancestor = [-1] * n
    idom = [-1] * n
    bucket: list[list[int]] = [[] for _ in range(n)]

    # Step 1: depth-first search from the root, assigning dfs numbers.
    size = 1
    semi[root] = 1
    vertex[1] = root
    cursor = [0] * n
    stack = [root]
    while stack:
        v = stack[-1]
        if cursor[v] < len(succ[v]):
            w = succ[v][cursor[v]]
            cursor[v] += 1
            if semi[w] == 0:
                size += 1
                semi[w] = size
                vertex[size] = w
                parent[w] = v
                stack.append(w)
        else:
            stack.pop()

    # Steps 2 & 3: semidominators and provisionally implied idoms,
    # processing vertices in reverse dfs order.
    for k in range(size, 1, -1):
        w = vertex[k]
        best = k
        for v in pred[w]:
            if semi[v] == 0:  # unreachable predecessor: cannot dominate w
                continue
            u = _eval(v, ancestor, label, semi)
            s = semi[u]
            if s < best:
                best = s
        semi[w] = best
        bucket[vertex[best]].append(w)
        pw = parent[w]
        ancestor[w] = pw  # link(pw, w)
        for v in bucket[pw]:
            u = _eval(v, ancestor, label, semi)
            idom[v] = u if semi[u] < semi[v] else pw
        bucket[pw] = []

    # Step 4: resolve idoms that were only implied in step 3.
    for k in range(2, size + 1):
        w = vertex[k]
        sd = vertex[semi[w]]
        if idom[w] != sd:
            idom[w] = idom[idom[w]]
    idom[root] = -1
    return DomResult(idom=idom, semi=semi, vertex=vertex, size=size)


def _eval(v: int, ancestor: list[int], label: list[int], semi: list[int]) -> int:
    """Lengauer-Tarjan EVAL with iterative path compression."""
    a = ancestor[v]
    if a == -1:
        return label[v]
    if ancestor[a] != -1:
        # compress(v), rewritten with an explicit stack: a recursive
        # implementation would overflow the interpreter stack on deep graphs.
        path = [v]
        x = a
        while ancestor[ancestor[x]] != -1:
            path.append(x)
            x = ancestor[x]
        for y in reversed(path):
            ay = ancestor[y]
            lay = label[ay]
            if semi[lay] < semi[label[y]]:
                label[y] = lay
            ancestor[y] = ancestor[ay]
    av = ancestor[v]
    lv = label[v]
    lav = label[av]
    return lv if semi[lav] >= semi[lv] else lav
