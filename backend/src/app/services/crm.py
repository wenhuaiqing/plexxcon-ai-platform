"""The CRM behind Bid Summary, behind one small interface.

The demo runs on SyntheticCrm: deals in the database, shaped like HubSpot deal
objects (dealname, amount, dealstage, closedate). HubSpotCrm is the same
interface over HubSpot's public CRM v3 API, used when HUBSPOT_TOKEN is set. It
is exercised here only against a mock transport (tests/test_crm.py) - this
demo has never called a real HubSpot portal, and says so on the page.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from src.app.services import audit, db
from src.settings import settings

OPEN_STAGES = ("qualifying", "tendering", "submitted")


class Crm(Protocol):
    name: str

    def open_deals(self) -> list[dict[str, Any]]: ...
    def get_deal(self, deal_id: str) -> dict[str, Any] | None: ...
    def update_deal(self, cur: Any, deal_id: str, amount_cents: int, stage: str, actor: str) -> None: ...


class SyntheticCrm:
    name = "Synthetic CRM (HubSpot-shaped deals in the demo database)"

    def open_deals(self) -> list[dict[str, Any]]:
        marks = ", ".join("?" for _ in OPEN_STAGES)
        return db.rows(f"""SELECT d.deal_id, d.bid_number, d.dealname, d.company, d.sector, d.amount_cents / 100.0 AS amount,
                                  d.dealstage, d.closedate, d.owner, b.bid_id
                           FROM crm_deal d LEFT JOIN bid b ON b.deal_id = d.deal_id
                           WHERE d.dealstage IN ({marks}) ORDER BY d.closedate""", list(OPEN_STAGES))

    def get_deal(self, deal_id: str) -> dict[str, Any] | None:
        found = db.rows("""SELECT deal_id, bid_number, dealname, company, sector, amount_cents / 100.0 AS amount, dealstage,
                                  closedate, owner FROM crm_deal WHERE deal_id = ?""", [deal_id])
        return found[0] if found else None

    def update_deal(self, cur: Any, deal_id: str, amount_cents: int, stage: str, actor: str) -> None:
        cur.execute("UPDATE crm_deal SET amount_cents = ?, dealstage = ?, updated_at = ? WHERE deal_id = ?",
                    [amount_cents, stage, audit.now(), deal_id])
        cur.execute("INSERT INTO crm_sync_log VALUES (?, 'push', ?, ?, ?)",
                    [audit.now(), deal_id, actor, f"amount set to ${amount_cents / 100:,.2f}, stage '{stage}'"])


class HubSpotCrm:
    """HubSpot CRM v3 (https://developers.hubspot.com/docs/api/crm/deals). Bid number
    and sector are assumed to be custom deal properties named bid_number and sector."""

    name = "HubSpot CRM v3"
    BASE = "https://api.hubapi.com"
    PROPS = "dealname,amount,dealstage,closedate,bid_number,sector,hubspot_owner_id"

    def __init__(self, token: str, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=self.BASE, timeout=10.0, transport=transport,
                                    headers={"Authorization": f"Bearer {token}"})

    @staticmethod
    def _shape(obj: dict[str, Any]) -> dict[str, Any]:
        p = obj.get("properties") or {}
        return {"deal_id": str(obj.get("id")), "bid_number": p.get("bid_number") or "", "dealname": p.get("dealname") or "",
                "company": "", "sector": p.get("sector") or "", "amount": float(p.get("amount") or 0),
                "dealstage": p.get("dealstage") or "", "closedate": (p.get("closedate") or "")[:10],
                "owner": p.get("hubspot_owner_id") or "", "bid_id": None}

    def open_deals(self) -> list[dict[str, Any]]:
        body = {"filterGroups": [{"filters": [{"propertyName": "dealstage", "operator": "NOT_IN",
                                               "values": ["closedwon", "closedlost"]}]}],
                "properties": self.PROPS.split(","), "limit": 100}
        r = self._client.post("/crm/v3/objects/deals/search", json=body)
        r.raise_for_status()
        return [self._shape(o) for o in r.json().get("results", [])]

    def get_deal(self, deal_id: str) -> dict[str, Any] | None:
        r = self._client.get(f"/crm/v3/objects/deals/{deal_id}", params={"properties": self.PROPS})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return self._shape(r.json())

    def update_deal(self, cur: Any, deal_id: str, amount_cents: int, stage: str, actor: str) -> None:
        r = self._client.patch(f"/crm/v3/objects/deals/{deal_id}",
                               json={"properties": {"amount": f"{amount_cents / 100:.2f}", "dealstage": stage}})
        r.raise_for_status()
        cur.execute("INSERT INTO crm_sync_log VALUES (?, 'push', ?, ?, ?)",
                    [audit.now(), deal_id, actor, f"HubSpot: amount ${amount_cents / 100:,.2f}, stage '{stage}'"])


def client() -> Crm:
    return HubSpotCrm(settings.hubspot_token) if settings.hubspot_token.strip() else SyntheticCrm()
