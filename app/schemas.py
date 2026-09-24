"""Request and response schemas for the relay audit API."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

MAX_NODES = 200_000
MAX_TERMINALS = 20_000
MAX_EDGES = 500_000


def _require_ascii(value: str) -> str:
    if not value.isascii():
        raise ValueError("node identifier must contain ASCII characters only")
    return value


NodeId = Annotated[
    str,
    StringConstraints(min_length=1),
    AfterValidator(_require_ascii),
]


class AuditRequest(BaseModel):
    """Emergency-stop relay network submitted for auditing."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[NodeId] = Field(
        min_length=2,
        max_length=MAX_NODES,
        description="Unique ASCII node identifiers.",
    )
    root: NodeId = Field(description="Root controller identifier; must be one of `nodes`.")
    terminals: list[NodeId] = Field(
        min_length=1,
        max_length=MAX_TERMINALS,
        description="Protected terminals (actuators); must be a subset of `nodes` "
        "and must not have outgoing edges.",
    )
    edges: list[tuple[NodeId, NodeId]] = Field(
        default_factory=list,
        max_length=MAX_EDGES,
        description="Directed edges as [source, target] pairs. Parallel edges are "
        "allowed, self-loops are forbidden.",
    )


class IdomEntry(BaseModel):
    node: str
    idom: str


class CriticalRelay(BaseModel):
    node: str
    dominated_terminals: int


class AuditResponse(BaseModel):
    """Audit of the subgraph reachable from the root controller."""

    unreachable_terminals: list[str] = Field(
        description="Protected terminals not reachable from the root, sorted by identifier."
    )
    immediate_dominators: list[IdomEntry] = Field(
        description="Immediate dominator of every reachable non-root node, "
        "sorted by node identifier."
    )
    critical_relays: list[CriticalRelay] = Field(
        description="Non-root, non-terminal relays dominating at least one protected "
        "terminal, sorted by node identifier."
    )
