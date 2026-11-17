"""Trade Planner: a second person decides, with feedback; the scope gates submission."""

from __future__ import annotations

import json

from tests.conftest import as_

from src.app.calc import trade as calc
from src.app.services import db, trades


def test_no_one_decides_their_own_request(client):
    author = db.scalar("SELECT author FROM tp_request WHERE request_id = 'TR-0003'")
    r = client.post("/api/trades/requests/TR-0003/review", json={"decision": "accepted", "feedback": "fine"}, headers=as_(author))
    assert r.status_code == 403
    assert db.scalar("SELECT status FROM tp_request WHERE request_id = 'TR-0003'") == "pending"
    assert db.scalar("SELECT count(*) FROM audit_log WHERE subject = 'TR-0003' AND outcome = 'refused'") == 1


def test_feedback_is_mandatory(client):
    r = client.post("/api/trades/requests/TR-0003/review", json={"decision": "accepted", "feedback": " "}, headers=as_("Construction manager"))
    assert r.status_code == 422


def test_reviewer_accepts_and_the_job_total_grows(client):
    before = {j["project_id"]: j for j in trades.jobs()}
    r = client.post("/api/trades/requests/TR-0003/review", json={"decision": "accepted", "feedback": "Agreed"}, headers=as_("Construction manager"))
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    after = {j["project_id"]: j for j in trades.jobs()}
    assert "2427" not in before and after["2427"]["accepted_requests"] == 1


def test_incomplete_scope_cannot_be_submitted(client):
    scope = {"project": {"project_id": "2440"}, "trades": [], "non_production": {}}
    r = client.post("/api/trades/requests", json={"title": "x", "scope": scope, "submit": True}, headers=as_("Site supervisor A"))
    assert r.status_code == 422 and "Complete first" in r.json()["detail"]


def test_revision_is_a_new_version_and_the_original_is_kept(client):
    r = client.post("/api/trades/requests/TR-0001/revise", headers=as_("Site supervisor A"))
    assert r.status_code == 200
    body = r.json()
    assert body["root_request_id"] == "TR-0001" and body["version"] == 2 and body["status"] == "draft"
    assert db.scalar("SELECT status FROM tp_request WHERE request_id = 'TR-0001'") == "accepted"


def test_submitted_request_is_not_edited(client):
    scope = json.loads(db.scalar("SELECT data_json FROM tp_request WHERE request_id = 'TR-0003'"))
    r = client.post("/api/trades/requests", json={"request_id": "TR-0003", "title": "x", "scope": scope}, headers=as_("Site supervisor B"))
    assert r.status_code == 409


def test_stored_numbers_are_the_servers(fresh_db):
    for case in trades.parity_cases():
        assert case["expected"] == calc.calculate(case["scope"], trades._rates())
    row = db.rows("SELECT data_json, total_cents FROM tp_request WHERE request_id = 'TR-0001'")[0]
    assert calc.calculate(json.loads(row["data_json"]), trades._rates())["total_cents"] == row["total_cents"]


def test_rate_change_needs_a_reason(client):
    r = client.put("/api/trades/library/FRM-010", json={"rate": "1.5", "reason": ""}, headers=as_("Estimating lead"))
    assert r.status_code == 422
    r = client.put("/api/trades/library/FRM-010", json={"rate": "1.5", "reason": "Measured on 2418"}, headers=as_("Estimating lead"))
    assert r.status_code == 200 and db.scalar("SELECT rate_x1000 FROM tp_rate WHERE rate_code = 'FRM-010'") == 1500
