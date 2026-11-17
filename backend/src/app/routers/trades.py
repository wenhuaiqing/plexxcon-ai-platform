"""Trade Planner. Calculation is open; saving, submitting and reviewing need the token."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.app.services import trades
from src.app.services.auth import actor, require_write

router = APIRouter(prefix="/api/trades", tags=["trade planner"])
write = [Depends(require_write)]


class Scope(BaseModel):
    scope: dict[str, Any]


class Save(Scope):
    request_id: str | None = Field(default=None, max_length=20)
    title: str = Field(default="", max_length=120)
    submit: bool = False


class Review(BaseModel):
    decision: str = Field(max_length=20)
    feedback: str = Field(default="", max_length=600)


class RateChange(BaseModel):
    rate: str = Field(max_length=20)
    reason: str = Field(default="", max_length=300)


@router.get("/reference")
def reference() -> dict:
    return trades.reference()


@router.get("/requests")
def requests(request: Request) -> list[dict]:
    return trades.requests(actor(request))


@router.get("/requests/{request_id}")
def request_detail(request_id: str) -> dict:
    return trades.request(request_id)


@router.get("/jobs")
def jobs() -> list[dict]:
    return trades.jobs()


@router.get("/parity")
def parity() -> list[dict]:
    return trades.parity_cases()


@router.get("/audit")
def audit_log() -> list[dict]:
    return trades.audit_log()


@router.post("/calculate")
def calculate(body: Scope) -> dict:
    """The server's numbers for a scope. Writes nothing; the wizard's preview is checked against this."""
    return trades.calculate(body.scope)


@router.post("/requests", dependencies=write)
def save(body: Save, request: Request) -> dict:
    return trades.save(actor(request), body.request_id, body.title, body.scope, body.submit)


@router.post("/requests/{request_id}/revise", dependencies=write)
def revise(request_id: str, request: Request) -> dict:
    return trades.revise(actor(request), request_id)


@router.post("/requests/{request_id}/review", dependencies=write)
def review(request_id: str, body: Review, request: Request) -> dict:
    return trades.review(actor(request), request_id, body.decision, body.feedback)


@router.put("/library/{rate_code}", dependencies=write)
def update_rate(rate_code: str, body: RateChange, request: Request) -> dict:
    return trades.update_rate(actor(request), rate_code, body.rate, body.reason)
