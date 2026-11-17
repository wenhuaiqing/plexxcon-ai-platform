"""Finance reports. Read-only."""

from __future__ import annotations

from fastapi import APIRouter

from src.app.services import finance

router = APIRouter(prefix="/api/finance", tags=["finance"])


@router.get("/options")
def options() -> dict:
    return finance.options()


@router.get("/pnl")
def pnl(entity: str = finance.GROUP, fin_year: int | None = None) -> dict:
    return finance.pnl(entity, fin_year)


@router.get("/balance-sheet")
def balance_sheet(entity: str = finance.GROUP, as_at: str | None = None) -> dict:
    return finance.balance_sheet(entity, as_at)


@router.get("/related-party")
def related_party(as_at: str | None = None) -> dict:
    return finance.related_party(as_at)


@router.get("/related-party/ledger")
def pair_ledger(creditor: str, debtor: str, as_at: str | None = None) -> dict:
    return finance.pair_ledger(creditor, debtor, as_at)
