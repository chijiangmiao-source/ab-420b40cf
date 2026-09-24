"""API-level tests: happy paths, sorting, and locatable input errors."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    # The context manager runs the lifespan, which flips the readiness flag
    # that /health reports on.
    with TestClient(app) as test_client:
        yield test_client


def _post(client, payload: dict):
    return client.post("/api/audit", json=payload)


def test_health_reports_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_diamond_bypass(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A", "B", "T"],
            "terminals": ["T"],
            "edges": [["R", "A"], ["R", "B"], ["A", "T"], ["B", "T"]],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["critical_relays"] == []
    assert body["unreachable_terminals"] == []
    assert body["immediate_dominators"] == [
        {"node": "A", "idom": "R"},
        {"node": "B", "idom": "R"},
        {"node": "T", "idom": "R"},
    ]


def test_series_critical_points(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A", "B", "T"],
            "terminals": ["T"],
            "edges": [["R", "A"], ["A", "B"], ["B", "T"]],
        },
    )
    assert response.status_code == 200
    assert response.json()["critical_relays"] == [
        {"node": "A", "dominated_terminals": 1},
        {"node": "B", "dominated_terminals": 1},
    ]


def test_parallel_edges(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A", "T"],
            "terminals": ["T"],
            "edges": [["R", "A"], ["R", "A"], ["A", "T"]],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["immediate_dominators"] == [
        {"node": "A", "idom": "R"},
        {"node": "T", "idom": "A"},
    ]
    assert body["critical_relays"] == [{"node": "A", "dominated_terminals": 1}]


def test_unreachable_terminals(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A", "T1", "T2"],
            "terminals": ["T1", "T2"],
            "edges": [["R", "A"], ["A", "T1"]],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["unreachable_terminals"] == ["T2"]
    assert body["critical_relays"] == [{"node": "A", "dominated_terminals": 1}]


def test_response_is_sorted_by_node_identifier(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "z9", "a1", "m5", "T"],
            "terminals": ["T"],
            "edges": [["R", "z9"], ["R", "a1"], ["z9", "m5"], ["a1", "m5"], ["m5", "T"]],
        },
    )
    assert response.status_code == 200
    body = response.json()
    nodes = [entry["node"] for entry in body["immediate_dominators"]]
    assert nodes == sorted(nodes)
    relays = [entry["node"] for entry in body["critical_relays"]]
    assert relays == sorted(relays)
    # m5 is the only single point of failure; z9/a1 are bypassed.
    assert body["critical_relays"] == [{"node": "m5", "dominated_terminals": 1}]


def test_duplicate_node_identifier_is_locatable(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A", "A"],
            "terminals": ["A"],
            "edges": [["R", "A"]],
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(e["loc"] == ["body", "nodes", 2] and e["type"] == "duplicate_identifier" for e in detail)


def test_duplicate_terminal_identifier_is_locatable(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A"],
            "terminals": ["A", "A"],
            "edges": [["R", "A"]],
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(e["loc"] == ["body", "terminals", 1] for e in detail)


def test_dangling_edge_endpoint_is_locatable(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A"],
            "terminals": ["A"],
            "edges": [["R", "GHOST"]],
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(
        e["loc"] == ["body", "edges", 0, 1] and e["type"] == "dangling_reference" for e in detail
    )


def test_dangling_root_is_locatable(client):
    response = _post(
        client, {"root": "NOPE", "nodes": ["R", "A"], "terminals": ["A"], "edges": [["R", "A"]]}
    )
    assert response.status_code == 422
    assert any(e["loc"] == ["body", "root"] for e in response.json()["detail"])


def test_dangling_terminal_is_locatable(client):
    response = _post(
        client, {"root": "R", "nodes": ["R", "A"], "terminals": ["T"], "edges": [["R", "A"]]}
    )
    assert response.status_code == 422
    assert any(e["loc"] == ["body", "terminals", 0] for e in response.json()["detail"])


def test_terminal_with_outgoing_edge_is_locatable(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A", "T"],
            "terminals": ["T"],
            "edges": [["R", "T"], ["T", "A"]],
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(
        e["loc"] == ["body", "edges", 1, 0] and e["type"] == "terminal_outgoing_edge"
        for e in detail
    )


def test_self_loop_is_locatable(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A"],
            "terminals": ["A"],
            "edges": [["R", "R"]],
        },
    )
    assert response.status_code == 422
    assert any(e["type"] == "self_loop" for e in response.json()["detail"])


def test_multiple_errors_are_all_reported_without_partial_audit(client):
    response = _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A", "A"],
            "terminals": ["A"],
            "edges": [["R", "GHOST"], ["A", "A"]],
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert len(body["detail"]) >= 3
    # No partial audit leaks into an error response.
    assert "immediate_dominators" not in body
    assert "critical_relays" not in body
    assert "unreachable_terminals" not in body


def test_schema_violations_are_rejected(client):
    # Non-ASCII identifier.
    assert _post(client, {"root": "R", "nodes": ["R", "节点"], "terminals": ["R"], "edges": []}).status_code == 422
    # Fewer than two nodes.
    assert _post(client, {"root": "R", "nodes": ["R"], "terminals": ["R"], "edges": []}).status_code == 422
    # Zero terminals.
    assert _post(client, {"root": "R", "nodes": ["R", "A"], "terminals": [], "edges": []}).status_code == 422
    # Empty identifier.
    assert _post(client, {"root": "R", "nodes": ["R", ""], "terminals": ["R"], "edges": []}).status_code == 422
    # Malformed edge tuple.
    assert _post(
        client, {"root": "R", "nodes": ["R", "A"], "terminals": ["A"], "edges": [["R", "A", "A"]]}
    ).status_code == 422
    # Unknown extra field.
    assert _post(
        client,
        {
            "root": "R",
            "nodes": ["R", "A"],
            "terminals": ["A"],
            "edges": [],
            "bogus": 1,
        },
    ).status_code == 422


def test_terminal_may_be_the_root(client):
    response = _post(client, {"root": "R", "nodes": ["R", "A"], "terminals": ["R"], "edges": []})
    assert response.status_code == 200
    body = response.json()
    assert body["unreachable_terminals"] == []
    assert body["immediate_dominators"] == []
    assert body["critical_relays"] == []
