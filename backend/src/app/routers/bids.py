"""Bid Summary. Reads are open; drafts and submission go through the write gate (auth.require_write)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from pydantic import BaseModel, Field

from src.app.calc import bid as calc
from src.app.services import bids
from src.app.services.auth import actor, require_write
from src.app.services.rate_limit import enforce_orb_rate_limit

router = APIRouter(prefix="/api/bids", tags=["bid summary"])
write = [Depends(require_write)]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Data(BaseModel):
    data: dict[str, Any]


class Start(BaseModel):
    bid_id: str | None = Field(default=None, max_length=20)
    blank: bool = False


class Save(Data):
    version: int
    overwrite: bool = False


class Link(BaseModel):
    deal_id: str = Field(max_length=40)


class Submit(BaseModel):
    acknowledge_warnings: bool = False


@router.get("")
def register() -> list[dict]:
    return bids.register()


@router.get("/reference")
def reference() -> dict:
    return bids.reference()


@router.get("/insights")
def insights() -> dict:
    return bids.insights()


@router.get("/audit")
def audit_log() -> list[dict]:
    return bids.audit_log()


@router.get("/drafts")
def drafts() -> list[dict]:
    return bids.drafts_list()


@router.get("/template.xlsx")
def template() -> Response:
    return Response(bids.workbook(calc.blank()), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="bid-summary-template.xlsx"'})


@router.post("/calculate")
def calculate(body: Data) -> dict:
    """The server's sums and the two-tier validation for any form state. Writes nothing."""
    return {"totals": calc.totals(body.data), "validation": calc.validate(body.data)}


@router.post("/preview.pdf", dependencies=[Depends(enforce_orb_rate_limit)])
def preview(body: Data) -> Response:
    return Response(bids.render_pdf(body.data, calc.totals(body.data), None, None, None), media_type="application/pdf")


@router.post("/workbook.xlsx", dependencies=[Depends(enforce_orb_rate_limit)])
def export_back(body: Data) -> Response:
    return Response(bids.workbook(body.data), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="bid-summary.xlsx"'})


@router.post("/import", dependencies=write)
async def import_workbook(file: UploadFile = File(...)) -> dict:
    return {"found": bids.read_workbook(await file.read(400_001)), "filename": file.filename}


@router.get("/{bid_id}/revisions/{rev}")
def revision(bid_id: str, rev: int) -> dict:
    return bids.revision(bid_id, rev)


@router.get("/{bid_id}/revisions/{rev}/summary.pdf")
def revision_pdf(bid_id: str, rev: int) -> Response:
    return Response(bids.revision_pdf(bid_id, rev), media_type="application/pdf")


@router.get("/{bid_id}/revisions/{rev}/workbook.xlsx")
def revision_workbook(bid_id: str, rev: int) -> Response:
    data = bids.revision(bid_id, rev)["data"]
    return Response(bids.workbook(data), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{data["project"]["bid_number"]}-rev{rev}.xlsx"'})


@router.post("/drafts", dependencies=write)
def start_draft(body: Start, request: Request) -> dict:
    return bids.start_draft(actor(request), body.bid_id, body.blank)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str) -> dict:
    return bids.get_draft(draft_id)


@router.put("/drafts/{draft_id}", dependencies=write)
def save_draft(draft_id: str, body: Save, request: Request) -> dict:
    return bids.save_draft(actor(request), draft_id, body.data, body.version, body.overwrite)


@router.delete("/drafts/{draft_id}", dependencies=write)
def discard_draft(draft_id: str, request: Request) -> dict:
    return bids.discard_draft(actor(request), draft_id)


@router.post("/drafts/{draft_id}/presence", dependencies=write)
def presence(draft_id: str, request: Request) -> list[dict]:
    return bids.presence(draft_id, actor(request))


@router.post("/drafts/{draft_id}/link", dependencies=write)
def link(draft_id: str, body: Link, request: Request) -> dict:
    return bids.link_crm(actor(request), draft_id, body.deal_id)


@router.post("/drafts/{draft_id}/submit", dependencies=write)
def submit(draft_id: str, body: Submit, request: Request) -> dict:
    return bids.submit(actor(request), draft_id, body.acknowledge_warnings)
