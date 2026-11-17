"""Material Supply Register. Reading and parsing are open; anything that commits needs the token."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from src.app.services import msr
from src.app.services.auth import actor, require_write
from src.app.services.rate_limit import enforce_orb_rate_limit

router = APIRouter(prefix="/api/msr", tags=["material supply register"])
write = [Depends(require_write)]


class Enrol(BaseModel):
    project_id: str = Field(max_length=12)


class BudgetLine(BaseModel):
    project_id: str = Field(max_length=12)
    reg: str = Field(alias="register", max_length=12)
    model_config = ConfigDict(populate_by_name=True)
    element: str = Field(max_length=60)
    sub_element: str = Field(default="", max_length=80)
    qty: str = Field(max_length=20)
    rate: str = Field(max_length=20)


class Forecast(BaseModel):
    fac_qty: str = Field(max_length=20)
    fac_rate: str = Field(max_length=20)
    reason: str = Field(default="", max_length=300)


class Price(BaseModel):
    project_id: str = Field(max_length=12)
    reg: str = Field(alias="register", max_length=12)
    model_config = ConfigDict(populate_by_name=True)
    supplier: str = Field(max_length=60)
    kind: str = Field(max_length=12)
    item: str = Field(max_length=60)
    unit: str = Field(default="", max_length=20)
    rate: str = Field(default="0", max_length=20)
    waived: bool = False
    effective_from: str = Field(max_length=10)


class Delivery(BaseModel):
    project_id: str = Field(max_length=12)
    reg: str = Field(alias="register", max_length=12)
    model_config = ConfigDict(populate_by_name=True)
    line_id: str = Field(max_length=12)
    description: str = Field(default="", max_length=80)
    supplier: str = Field(default="", max_length=60)
    item: str = Field(default="", max_length=60)
    scheduled_date: str = Field(max_length=10)
    planned_qty: str = Field(max_length=20)


class Delete(BaseModel):
    kind: str = Field(max_length=20)
    id: str = Field(max_length=20)
    restore: bool = False


class Commit(BaseModel):
    kind: str | None = Field(default=None, max_length=12)
    supplier: str | None = Field(default=None, max_length=60)
    parser: str | None = Field(default=None, max_length=40)
    delivery_id: str | None = Field(default=None, max_length=12)
    fields: dict[str, Any] = Field(default_factory=dict)
    lines: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    rates: list[dict[str, Any]] = Field(default_factory=list, max_length=60)


@router.get("/portfolio")
def portfolio() -> dict:
    return msr.portfolio()


@router.get("/jobs")
def search(q: str = "") -> list[dict]:
    return msr.search_jobs(q[:20])


@router.get("/projects/{project_id}")
def workspace(project_id: str, register: str = "concrete") -> dict:
    return msr.workspace(project_id, register)


@router.get("/invoices/{invoice_id}")
def invoice(invoice_id: str) -> dict:
    return msr.invoice_detail(invoice_id)


@router.get("/invoices/{invoice_id}/source.pdf")
def invoice_pdf(invoice_id: str) -> Response:
    return Response(msr.invoice_pdf(invoice_id), media_type="application/pdf")


@router.get("/documents/{doc_id}/source.pdf")
def document_pdf(doc_id: str) -> Response:
    return Response(msr.document_pdf(doc_id), media_type="application/pdf")


@router.post("/documents/{doc_id}/parse", dependencies=[Depends(enforce_orb_rate_limit)])
def parse(doc_id: str) -> dict:
    """Read the PDF into a proposal for the review dialog. Commits nothing."""
    return msr.parse_document(doc_id)


@router.post("/enrol", dependencies=write)
def enrol(body: Enrol, request: Request) -> dict:
    return msr.enrol(actor(request), body.project_id)


@router.post("/budget-lines", dependencies=write)
def add_budget_line(body: BudgetLine, request: Request) -> dict:
    return msr.add_budget_line(actor(request), body.project_id, body.reg, body.element, body.sub_element, body.qty, body.rate)


@router.post("/budget-lines/{line_id}/forecast", dependencies=write)
def set_forecast(line_id: str, body: Forecast, request: Request) -> dict:
    return msr.set_forecast(actor(request), line_id, body.fac_qty, body.fac_rate, body.reason)


@router.post("/prices", dependencies=write)
def add_price(body: Price, request: Request) -> dict:
    return msr.add_price(actor(request), body.project_id, body.reg, body.supplier, body.kind, body.item, body.unit,
                         body.rate, body.waived, body.effective_from)


@router.post("/deliveries", dependencies=write)
def schedule_delivery(body: Delivery, request: Request) -> dict:
    return msr.schedule_delivery(actor(request), body.project_id, body.reg, body.line_id, body.description, body.supplier,
                                 body.item, body.scheduled_date, body.planned_qty)


@router.post("/delete", dependencies=write)
def soft_delete(body: Delete, request: Request) -> dict:
    return msr.soft_delete(actor(request), body.kind, body.id, body.restore)


@router.post("/documents/{doc_id}/commit", dependencies=write)
def commit(doc_id: str, body: Commit, request: Request) -> dict:
    return msr.commit_document(actor(request), doc_id, body.model_dump())


@router.post("/projects/{project_id}/upload", dependencies=[*write, Depends(enforce_orb_rate_limit)])
async def upload(project_id: str, request: Request, reg: str = Form(..., alias="register"), file: UploadFile = File(...)) -> dict:
    return msr.upload(actor(request), project_id, reg, file.filename or "upload.pdf", await file.read(1_500_001))
