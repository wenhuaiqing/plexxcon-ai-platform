"""Every defect the generator seeds (pipeline/reference.py SEEDED) is found
from the data by the services - never by reading the reference."""

from __future__ import annotations

from src.app.pipeline import reference as ref
from src.app.services import db, finance, msr


def _pair(rp, creditor, debtor):
    return next(p for p in rp["pairs"] if p["creditor"] == creditor and p["debtor"] == debtor)


def test_one_sided_intercompany_charge_is_found(fresh_db):
    s = ref.SEEDED["rp_one_sided"]
    pair = _pair(finance.related_party(), s["creditor"], s["debtor"])
    hit = [f for f in pair["findings"] if f["kind"] == "one_sided"]
    assert len(hit) == 1 and hit[0]["amount"] * 100 == s["amount_cents"] and hit[0]["date"].startswith(s["month"])


def test_wrong_party_booking_is_found_from_both_sides(fresh_db):
    s = ref.SEEDED["rp_wrong_party"]
    rp = finance.related_party()
    hit = [f for f in _pair(rp, s["creditor"], s["debtor"])["findings"] if f["kind"] == "wrong_party"]
    assert len(hit) == 1 and hit[0]["booked_to"] == s["booked_to"]
    other = [f for f in _pair(rp, s["booked_to"], s["debtor"])["findings"] if f["kind"] == "wrong_party_other_half"]
    assert len(other) == 1 and other[0]["amount"] * 100 == s["amount_cents"]


def test_month_end_payment_is_called_timing(fresh_db):
    s = ref.SEEDED["rp_timing"]
    hit = [f for f in _pair(finance.related_party(), s["creditor"], s["debtor"])["findings"] if f["kind"] == "timing"]
    assert len(hit) == 1 and abs(hit[0]["amount"]) * 100 == s["amount_cents"]


def test_pairs_without_a_seeded_break_agree(fresh_db):
    rp = finance.related_party()
    broken = {(s["creditor"], s["debtor"]) for s in (ref.SEEDED["rp_one_sided"], ref.SEEDED["rp_timing"], ref.SEEDED["rp_wrong_party"])}
    broken.add((ref.SEEDED["rp_wrong_party"]["booked_to"], ref.SEEDED["rp_wrong_party"]["debtor"]))
    for p in rp["pairs"]:
        assert p["agrees"] == ((p["creditor"], p["debtor"]) not in broken), p


def _invoices(project):
    return db.rows("SELECT invoice_id, invoice_no, recon_status, variance_bp, open_lines FROM msr_invoice WHERE project_id = ?", [project])


def test_rate_overcharge_turns_an_invoice_amber_not_green(fresh_db):
    rows = [r for r in _invoices(ref.SEEDED["msr_rate_overcharge"]["project"]) if "2606" in r["invoice_no"] and r["invoice_no"].startswith("CPM")]
    assert len(rows) == 1
    assert rows[0]["recon_status"] == "amber" and rows[0]["open_lines"] == 0
    assert ref.RECON_GREEN_BP <= rows[0]["variance_bp"] <= ref.RECON_AMBER_BP


def test_docket_billed_twice_is_red_with_duplicate_lines(fresh_db):
    rows = [r for r in _invoices(ref.SEEDED["msr_duplicate_docket"]["project"]) if "ADJ" in r["invoice_no"]]
    assert rows and rows[0]["recon_status"] == "red"
    lines = db.rows("SELECT match_status FROM msr_invoice_line WHERE invoice_id = ?", [rows[0]["invoice_id"]])
    assert {ln["match_status"] for ln in lines} == {"duplicate"}


def test_docket_not_on_the_register_is_an_open_line(fresh_db):
    project = ref.SEEDED["msr_unmatched_docket"]["project"]
    lines = db.rows("""SELECT l.match_status FROM msr_invoice_line l JOIN msr_invoice i USING (invoice_id)
                       WHERE i.project_id = ? AND l.match_status = 'unmatched'""", [project])
    assert len(lines) == 1


def test_unlisted_waiting_time_is_a_small_amber(fresh_db):
    project = ref.SEEDED["msr_waiting_time"]["project"]
    rows = db.rows("""SELECT i.recon_status, i.variance_bp FROM msr_invoice i JOIN msr_invoice_line l USING (invoice_id)
                      WHERE i.project_id = ? AND l.match_status = 'unlisted'""", [project])
    assert rows and rows[0]["recon_status"] == "amber" and rows[0]["variance_bp"] < ref.RECON_GREEN_BP


def test_delivered_past_forecast_shows_on_the_dashboard(fresh_db):
    w = msr.workspace(ref.SEEDED["msr_fac_overrun"]["project"], "concrete")
    assert "Footings" in w["dashboard"]["over_forecast"]


def test_every_other_invoice_is_green(fresh_db):
    bad = db.scalar("SELECT count(*) FROM msr_invoice WHERE recon_status <> 'green'")
    assert bad == 4
