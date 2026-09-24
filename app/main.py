"""FastAPI application exposing the relay-network audit endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.audit import run_audit
from app.schemas import AuditRequest, AuditResponse
from app.validation import AuditInputError, collect_input_errors


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.ready = True
    yield
    app.state.ready = False


app = FastAPI(
    title="Emergency-Stop Relay Network Auditor",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(AuditInputError)
async def audit_input_error_handler(_request: Request, exc: AuditInputError) -> JSONResponse:
    # Refuse the whole audit: never return partial results for bad input.
    return JSONResponse(status_code=422, content={"detail": exc.errors})


@app.get("/health", tags=["meta"])
def health(request: Request) -> JSONResponse:
    if getattr(request.app.state, "ready", False):
        return JSONResponse(status_code=200, content={"status": "ok"})
    return JSONResponse(status_code=503, content={"status": "unavailable"})


@app.post("/api/audit", response_model=AuditResponse, tags=["audit"])
def audit(req: AuditRequest) -> dict:
    errors = collect_input_errors(req)
    if errors:
        raise AuditInputError(errors)
    return run_audit(req.nodes, req.root, req.terminals, req.edges)
