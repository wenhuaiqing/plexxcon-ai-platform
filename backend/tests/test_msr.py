"""Material Supply Register: nothing a parser reads is recorded until a person
confirms it; reconciliation follows every change; deletes are soft."""

from __future__ import annotations

import pytest
from tests.conftest import WRITE

from src.app.services import db, msr, supplier_docs


def _doc(kind, supplier=None):
    sql = "SELECT doc_id FROM msr_document WHERE kind = ? AND status = 'inbox'" + (" AND supplier = ?" if supplier else "") + " ORDER BY doc_id"
    return db.scalar(sql, [kind, supplier] if supplier else [kind])


@pytest.mark.parametrize("supplier", ["Coastal Premix", "Ridgeline Concrete"])
def test_each_supplier_parser_reads_its_docket(fresh_db, supplier):
    p = msr.parse_document(_doc("docket", supplier))
    f = p["fields"]
    assert p["parser"] != "none" and f["docket_no"] and f["date"] and f["qty"] and f["job"]
    assert p["suggested_delivery_id"]


def test_unknown_layout_without_a_model_is_handed_to_a_person(fresh_db):
    p = msr.parse_document(_doc("docket", "Hinterland Valley Concrete"))
    assert p["parser"] == "none" and p["fields"] == {} and "by hand" in p["note"]


def test_ai_fallback_drops_values_not_in_the_document(fresh_db, monkeypatch):
    from src.app.services import llm
    monkeypatch.setattr(llm, "configured", lambda: True)
    monkeypatch.setattr(llm, "chat_structured", lambda messages, model, **k: model(
        supplier="Hinterland Valley Concrete", docket_no="HV-9931", date="2026-11-12", job="2440", item="N32/20", qty="9.99"))
    p = msr.parse_document(_doc("docket", "Hinterland Valley Concrete"))
    assert p["parser"] == "ai_fallback"
    assert p["fields"]["docket_no"] == "HV-9931" and p["fields"]["qty"] == ""   # 9.99 is not on the docket
    assert "qty" in p["note"]


def test_parsing_commits_nothing(fresh_db):
    before = db.scalar("SELECT count(*) FROM msr_docket")
    msr.parse_document(_doc("docket", "Coastal Premix"))
    assert db.scalar("SELECT count(*) FROM msr_docket") == before


def test_confirmed_docket_rolls_up_and_cannot_be_recorded_twice(client):
    doc = _doc("docket", "Coastal Premix")
    p = msr.parse_document(doc)
    body = {"kind": "docket", "supplier": p["supplier"], "parser": p["parser"], "delivery_id": p["suggested_delivery_id"], "fields": p["fields"]}
    line = db.scalar("SELECT line_id FROM msr_delivery WHERE delivery_id = ?", [p["suggested_delivery_id"]])
    before = db.scalar("SELECT coalesce(sum(k.qty_x100), 0) FROM msr_docket k JOIN msr_delivery v USING (delivery_id) WHERE v.line_id = ?", [line])
    assert client.post(f"/api/msr/documents/{doc}/commit", json=body, headers=WRITE).status_code == 200
    after = db.scalar("SELECT sum(k.qty_x100) FROM msr_docket k JOIN msr_delivery v USING (delivery_id) WHERE v.line_id = ?", [line])
    assert after - before == round(float(p["fields"]["qty"]) * 100)
    again = client.post(f"/api/msr/documents/{doc}/commit", json=body, headers=WRITE)
    assert again.status_code == 409


def test_invoice_reconciles_once_its_dockets_are_confirmed(client):
    inv = _doc("invoice")
    p = msr.parse_document(inv)
    assert any(line["prematch"] is None for line in p["lines"])
    r = client.post(f"/api/msr/documents/{inv}/commit", json={"kind": "invoice", **{k: p[k] for k in ("supplier", "parser", "fields", "lines")}}, headers=WRITE)
    assert r.status_code == 200
    status = db.scalar("SELECT recon_status FROM msr_invoice WHERE invoice_id = ?", [r.json()["ref"]])
    assert status == "red"   # its dockets are still in the inbox
    project = db.scalar("SELECT project_id FROM msr_document WHERE doc_id = ?", [inv])
    for d in db.rows("SELECT doc_id FROM msr_document WHERE kind = 'docket' AND status = 'inbox' AND project_id = ?", [project]):
        q = msr.parse_document(d["doc_id"])
        client.post(f"/api/msr/documents/{d['doc_id']}/commit", json={"kind": "docket", "supplier": q["supplier"], "parser": q["parser"],
                    "delivery_id": q["suggested_delivery_id"], "fields": q["fields"]}, headers=WRITE)
    assert db.scalar("SELECT recon_status FROM msr_invoice WHERE invoice_id = ?", [r.json()["ref"]]) == "green"


def test_quote_adds_dated_rates_and_closes_the_old_ones(client):
    doc = _doc("quote")
    p = msr.parse_document(doc)
    assert len(p["rates"]) == 5
    r = client.post(f"/api/msr/documents/{doc}/commit", json={"kind": "quote", "supplier": p["supplier"], "fields": p["fields"], "rates": p["rates"]}, headers=WRITE)
    assert r.status_code == 200
    open_rates = db.rows("""SELECT item, effective_from FROM msr_price WHERE project_id = '2418' AND supplier = 'Coastal Premix'
                            AND kind = 'base' AND item = 'N32/20' AND effective_to IS NULL AND deleted_at IS NULL""")
    assert [str(x["effective_from"])[:10] for x in open_rates] == ["2027-01-01"]


def test_forecast_change_needs_a_reason(client):
    line = db.scalar("SELECT line_id FROM msr_budget_line WHERE project_id = '2418' ORDER BY line_id LIMIT 1")
    assert client.post(f"/api/msr/budget-lines/{line}/forecast", json={"fac_qty": "70", "fac_rate": "280", "reason": ""}, headers=WRITE).status_code == 422
    assert client.post(f"/api/msr/budget-lines/{line}/forecast", json={"fac_qty": "70", "fac_rate": "280", "reason": "Rev C drawings"}, headers=WRITE).status_code == 200
    assert db.scalar("SELECT budget_qty_x100 <> fac_qty_x100 FROM msr_budget_line WHERE line_id = ?", [line])


def test_soft_delete_hides_from_totals_and_undo_restores(client):
    inv = db.scalar("SELECT invoice_id FROM msr_invoice WHERE project_id = '2418' AND register = 'concrete' ORDER BY invoice_id LIMIT 1")
    total = msr.workspace("2418", "concrete")["dashboard"]["invoiced"]
    assert client.post("/api/msr/delete", json={"kind": "invoice", "id": inv}, headers=WRITE).status_code == 200
    assert msr.workspace("2418", "concrete")["dashboard"]["invoiced"] < total
    assert db.scalar("SELECT count(*) FROM msr_invoice WHERE invoice_id = ?", [inv]) == 1
    assert client.post("/api/msr/delete", json={"kind": "invoice", "id": inv, "restore": True}, headers=WRITE).status_code == 200
    assert msr.workspace("2418", "concrete")["dashboard"]["invoiced"] == total


def test_budget_line_with_deliveries_cannot_be_deleted(client):
    line = db.scalar("SELECT line_id FROM msr_delivery WHERE project_id = '2418' LIMIT 1")
    assert client.post("/api/msr/delete", json={"kind": "budget_line", "id": line}, headers=WRITE).status_code == 409


def test_enrolment_scopes_the_register(client):
    assert client.get("/api/msr/projects/2444").status_code == 404
    assert client.post("/api/msr/enrol", json={"project_id": "2444"}, headers=WRITE).status_code == 200
    assert client.get("/api/msr/projects/2444").status_code == 200
    assert client.post("/api/msr/enrol", json={"project_id": "2444"}, headers=WRITE).status_code == 409


def test_every_seeded_invoice_pdf_parses_back_to_its_total(fresh_db):
    for inv in db.rows("SELECT invoice_id, supplier, total_cents FROM msr_invoice WHERE source_doc_id IS NULL LIMIT 12"):
        p = supplier_docs.parse(msr.invoice_pdf(inv["invoice_id"]))
        assert p["parser"] != "none", inv
        assert round(float(p["fields"]["total"]) * 100) == inv["total_cents"], inv
