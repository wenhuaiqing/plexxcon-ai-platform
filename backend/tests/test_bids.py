"""Bid Summary: revisions are immutable, the last save never silently wins,
and the two validation tiers behave as stated."""

from __future__ import annotations

from tests.conftest import WRITE, as_

from src.app.services import bids, db
from src.settings import settings


def _start(client, actor="Estimator A", **body):
    r = client.post("/api/bids/drafts", json=body, headers=as_(actor))
    assert r.status_code == 200, r.text
    return r.json()


def test_open_demo_lets_visitors_write_and_the_token_gate_still_works(client, monkeypatch):
    # The open demo: no token, the write goes through, and the actor is still recorded.
    r = client.post("/api/bids/drafts", json={"blank": True}, headers={"X-Actor": "Visitor"})
    assert r.status_code == 200, r.text
    # Closed: the same write needs the operator's token.
    monkeypatch.setattr(settings, "public_writes", False)
    assert client.post("/api/bids/drafts", json={"blank": True}).status_code == 401
    assert client.post("/api/bids/drafts", json={"blank": True}, headers=WRITE).status_code == 200


def test_open_writes_are_rate_limited(client, monkeypatch):
    from src.app.services import rate_limit
    monkeypatch.setattr(rate_limit, "_write_per_ip", rate_limit.SlidingWindowLimiter(2, 300))
    codes = [client.post("/api/bids/drafts", json={"blank": True}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_new_revision_from_latest_and_submit(client):
    d = _start(client, bid_id="BID-001")
    before = db.scalar("SELECT latest_revision FROM bid WHERE bid_id = 'BID-001'")
    d["data"]["margin"]["margin_pct"] = "9.5"
    r = client.put(f"/api/bids/drafts/{d['draft_id']}", json={"data": d["data"], "version": d["version"]}, headers=as_("Estimator A"))
    assert r.status_code == 200
    r = client.post(f"/api/bids/drafts/{d['draft_id']}/submit", json={}, headers=as_("Estimator A"))
    assert r.status_code == 200, r.text
    assert r.json()["revision"] == before + 1
    assert db.scalar("SELECT count(*) FROM bid_revision WHERE bid_id = 'BID-001' AND is_latest") == 1
    assert db.scalar("SELECT count(*) FROM bid_revision_pdf WHERE bid_id = 'BID-001'") == 1
    assert db.scalar("SELECT count(*) FROM bid_draft WHERE draft_id = ?", [d["draft_id"]]) == 0
    assert db.scalar("SELECT dealstage FROM crm_deal d JOIN bid b USING (deal_id) WHERE b.bid_id = 'BID-001'") == "submitted"
    first = db.scalar("SELECT margin_bp FROM bid_revision WHERE bid_id = 'BID-001' AND revision = 1")
    assert first != 950  # revision 1 untouched


def test_stale_save_is_a_conflict_not_an_overwrite(client):
    d = _start(client, bid_id="BID-002")
    ok = client.put(f"/api/bids/drafts/{d['draft_id']}", json={"data": d["data"], "version": d["version"]}, headers=as_("Estimator B"))
    assert ok.status_code == 200
    stale = client.put(f"/api/bids/drafts/{d['draft_id']}", json={"data": d["data"], "version": d["version"]}, headers=as_("Estimator A"))
    assert stale.status_code == 409 and stale.json()["detail"]["kind"] == "conflict"
    forced = client.put(f"/api/bids/drafts/{d['draft_id']}", json={"data": d["data"], "version": d["version"], "overwrite": True}, headers=as_("Estimator A"))
    assert forced.status_code == 200
    assert db.scalar("SELECT count(*) FROM audit_log WHERE action = 'conflict overwrite'") == 1


def test_hard_stops_refuse_and_soft_warnings_ask(client):
    d = _start(client, blank=True)
    r = client.post(f"/api/bids/drafts/{d['draft_id']}/submit", json={}, headers=WRITE)
    assert r.status_code == 422
    assert db.scalar("SELECT count(*) FROM audit_log WHERE outcome = 'refused' AND action = 'submit revision'") == 1
    data = d["data"]
    data["project"].update({"bid_name": "Test", "bid_number": "B-9999", "gross_building_area": "500"})
    data["programme"].update({"site_establishment": "2027-01-04", "practical_completion": "2027-06-30"})
    client.put(f"/api/bids/drafts/{d['draft_id']}", json={"data": data, "version": d["version"]}, headers=WRITE)
    r = client.post(f"/api/bids/drafts/{d['draft_id']}/submit", json={}, headers=WRITE)
    assert r.status_code == 409 and len(r.json()["detail"]["soft"]) == 4
    r = client.post(f"/api/bids/drafts/{d['draft_id']}/submit", json={"acknowledge_warnings": True}, headers=WRITE)
    assert r.status_code == 200 and r.json()["revision"] == 1


def test_crm_link_fills_the_header_and_shares_the_draft(client):
    d = _start(client, blank=True)
    deal = db.rows("SELECT deal_id, bid_number FROM crm_deal WHERE bid_number = 'B-2638'")[0]
    r = client.post(f"/api/bids/drafts/{d['draft_id']}/link", json={"deal_id": deal["deal_id"]}, headers=WRITE)
    assert r.status_code == 200 and r.json()["data"]["project"]["bid_number"] == "B-2638"


def test_second_shared_draft_for_a_tender_is_refused(client):
    d = _start(client, blank=True)
    deal = db.scalar("SELECT deal_id FROM crm_deal WHERE bid_number = 'B-2634'")
    r = client.post(f"/api/bids/drafts/{d['draft_id']}/link", json={"deal_id": deal}, headers=WRITE)
    assert r.status_code == 409


def test_workbook_round_trip(fresh_db):
    data = bids.revision("BID-001")["data"]
    found = bids.read_workbook(bids.workbook(data))
    assert found["project"]["bid_name"] == data["project"]["bid_name"]
    assert [x["cost_code"] for x in found["direct"]] == [x["cost_code"] for x in data["direct"]]
    assert [float(x["amount"]) for x in found["direct"]] == [float(x["amount"]) for x in data["direct"]]
