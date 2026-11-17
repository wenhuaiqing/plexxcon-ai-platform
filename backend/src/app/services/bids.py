"""Bid Summary: the one-page commercial summary of a tender, with every price
change locked as an immutable, numbered revision.

It sits on top of the estimator's workbook rather than replacing it: import
the summary tab, paste blocks into the grids, export back. Summary level only.

What is deliberately not here: a sign-off workflow. Submitting is a record,
not an approval. And no live co-editing: a shared draft carries a version, a
save against a stale version is refused with the other person's copy, and the
editor chooses - the last save never silently wins.
"""

from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from fpdf import FPDF

from src.app.calc import bid as calc
from src.app.pipeline import reference as ref
from src.app.pipeline.generate import cost_line_rows, revision_row
from src.app.services import audit, crm, db

SYSTEM = "bid_summary"
PRESENCE_SECONDS = 90


def reference() -> dict[str, Any]:
    c = crm.client()
    return {
        "sections": ref.BID_SECTIONS, "sectors": ref.SECTORS,
        "cost_codes": [{"code": code, "description": d, "group": g} for code, d, g in ref.COST_CODES],
        "hard_stops": [{"field": f, "label": label} for f, label in ref.BID_HARD_STOPS],
        "soft_warnings": [{"field": f, "label": label} for f, label in ref.BID_SOFT_WARNINGS],
        "bid_gates": ["Gate 1 - Expression of interest", "Gate 2 - Tender", "Gate 3 - Final price"],
        "blank": calc.blank(), "crm": {"name": c.name, "deals": c.open_deals()},
        "people": ref.PEOPLE["estimators"],
    }


# ---------------------------------------------------------------- register --
def register() -> list[dict]:
    rows = db.rows("""
        SELECT b.bid_id, b.bid_number, b.bid_name, b.sector, b.latest_revision, r.client, r.submitted_at, r.submitted_by,
               r.final_ex_cents / 100.0 AS final_ex, r.final_inc_cents / 100.0 AS final_inc, r.margin_bp / 100.0 AS margin_pct,
               r.rate_per_m2_cents / 100.0 AS rate_per_m2, r.gross_building_area_m2, r.submission_date, d.dealstage AS crm_stage,
               (SELECT count(*) FROM bid_revision x WHERE x.bid_id = b.bid_id) AS revisions
        FROM bid b JOIN bid_revision r ON r.bid_id = b.bid_id AND r.is_latest
        LEFT JOIN crm_deal d ON d.deal_id = b.deal_id
        ORDER BY r.submitted_at DESC""")
    drafts = {d["bid_id"]: d for d in drafts_list() if d["bid_id"]}
    for row in rows:
        draft = drafts.get(row["bid_id"])
        row["in_progress"] = {"draft_id": draft["draft_id"], "by": draft["updated_by"], "updated_at": draft["updated_at"]} if draft else None
    return rows


def revision(bid_id: str, rev: int | None = None) -> dict[str, Any]:
    found = db.rows("SELECT * FROM bid_revision WHERE bid_id = ? " + ("AND revision = ?" if rev else "AND is_latest"),
                    [bid_id, rev] if rev else [bid_id])
    if not found:
        raise HTTPException(status_code=404, detail="No such revision.")
    r = found[0]
    data = json.loads(r.pop("data_json"))
    history = db.rows("""SELECT revision, is_latest, submitted_at, submitted_by, final_ex_cents / 100.0 AS final_ex,
                                margin_bp / 100.0 AS margin_pct FROM bid_revision WHERE bid_id = ? ORDER BY revision DESC""", [bid_id])
    return {"bid_id": bid_id, "revision": r["revision"], "is_latest": r["is_latest"], "submitted_at": r["submitted_at"],
            "submitted_by": r["submitted_by"], "warnings_acknowledged": r["warnings_acknowledged"],
            "data": data, "totals": calc.totals(data), "history": history}


# ------------------------------------------------------------------ drafts --
def drafts_list() -> list[dict]:
    return db.rows("""SELECT draft_id, bid_id, deal_id, owner, base_revision, version, created_at, updated_at, updated_by,
                             json_extract_string(data_json, '$.project.bid_name') AS bid_name,
                             json_extract_string(data_json, '$.project.bid_number') AS bid_number
                      FROM bid_draft ORDER BY updated_at DESC""")


def _draft(cur: Any, draft_id: str) -> dict[str, Any]:
    row = cur.execute("""SELECT draft_id, bid_id, deal_id, owner, base_revision, version, data_json, updated_at, updated_by
                         FROM bid_draft WHERE draft_id = ?""", [draft_id]).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="That draft no longer exists. It may have been submitted or discarded.")
    keys = ["draft_id", "bid_id", "deal_id", "owner", "base_revision", "version", "data_json", "updated_at", "updated_by"]
    d = dict(zip(keys, row))
    d["data"] = json.loads(d.pop("data_json"))
    d["updated_at"] = d["updated_at"].isoformat()
    return d


def get_draft(draft_id: str) -> dict[str, Any]:
    with db.writing() as cur:
        d = _draft(cur, draft_id)
    return {**d, "totals": calc.totals(d["data"]), "validation": calc.validate(d["data"]), "others": presence(draft_id, "")}


def start_draft(actor: str, bid_id: str | None, blank: bool) -> dict[str, Any]:
    """New revision from the latest, or a new blank summary. One shared draft per tender."""
    with db.writing() as cur:
        if bid_id:
            existing = cur.execute("SELECT draft_id FROM bid_draft WHERE bid_id = ?", [bid_id]).fetchone()
            if existing:
                return {**_draft(cur, existing[0]), "resumed": True}
            latest = cur.execute("SELECT revision, data_json FROM bid_revision WHERE bid_id = ? AND is_latest", [bid_id]).fetchone()
            if not latest:
                raise HTTPException(status_code=404, detail="No such tender.")
            deal = cur.execute("SELECT deal_id FROM bid WHERE bid_id = ?", [bid_id]).fetchone()[0]
            base, data = latest[0], json.loads(latest[1])
        else:
            deal, base, data = None, 0, calc.blank()
            data["project"]["estimator"] = actor
        n = cur.execute("SELECT coalesce(max(CAST(substr(draft_id, 5) AS INTEGER)), 0) + 1 FROM bid_draft").fetchone()[0]
        draft_id = f"DRF-{n:04d}"
        now = audit.now()
        cur.execute("INSERT INTO bid_draft VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                    [draft_id, bid_id, deal, actor, base, json.dumps(data, sort_keys=True), now, now, actor])
        audit.record(cur, actor, SYSTEM, draft_id, "start draft",
                     detail=("New revision from revision " + str(base)) if bid_id else "New blank summary")
        return {**_draft(cur, draft_id), "resumed": False}


def save_draft(actor: str, draft_id: str, data: dict[str, Any], version: int, overwrite: bool) -> dict[str, Any]:
    with db.writing() as cur:
        current = _draft(cur, draft_id)
        if current["version"] != version:
            if not overwrite:
                # Not recorded as a refusal: nothing was attempted against a rule. The editor chooses.
                raise HTTPException(status_code=409, detail={
                    "kind": "conflict",
                    "message": f"{current['updated_by']} saved this draft after you opened it. Nothing of theirs has been overwritten.",
                    "theirs": current})
            audit.record(cur, actor, SYSTEM, draft_id, "conflict overwrite",
                         detail=f"Kept own copy over version {current['version']} saved by {current['updated_by']}")
        now = audit.now()
        cur.execute("UPDATE bid_draft SET data_json = ?, version = version + 1, updated_at = ?, updated_by = ? WHERE draft_id = ?",
                    [json.dumps(data, sort_keys=True), now, actor, draft_id])
        if current["updated_by"] != actor and current["version"] == version:
            audit.record(cur, actor, SYSTEM, draft_id, "draft handoff", detail=f"Picked up from {current['updated_by']}")
        return {"draft_id": draft_id, "version": current["version"] + 1, "updated_at": now.isoformat(), "updated_by": actor,
                "totals": calc.totals(data), "validation": calc.validate(data)}


def link_crm(actor: str, draft_id: str, deal_id: str) -> dict[str, Any]:
    """Picking the opportunity fills bid number, name and sector, and makes this
    the shared draft for that tender."""
    deal = crm.client().get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="That opportunity is not in the CRM.")
    with db.writing() as cur:
        d = _draft(cur, draft_id)
        bid = cur.execute("SELECT bid_id FROM bid WHERE deal_id = ?", [deal_id]).fetchone()
        other = cur.execute("SELECT draft_id, updated_by FROM bid_draft WHERE deal_id = ? AND draft_id <> ?", [deal_id, draft_id]).fetchone()
        if other:
            audit.refuse(cur, actor, SYSTEM, draft_id, "link to CRM",
                         f"{other[1]} already has the shared draft for {deal['bid_number']} open. Resume that draft instead.")
        data = d["data"]
        data["project"].update({"bid_number": deal["bid_number"], "bid_name": deal["dealname"], "sector": deal["sector"],
                                "client": data["project"].get("client") or deal["company"]})
        cur.execute("""UPDATE bid_draft SET deal_id = ?, bid_id = ?, data_json = ?, version = version + 1, updated_at = ?,
                       updated_by = ? WHERE draft_id = ?""",
                    [deal_id, bid[0] if bid else None, json.dumps(data, sort_keys=True), audit.now(), actor, draft_id])
        cur.execute("INSERT INTO crm_sync_log VALUES (?, 'pull', ?, ?, ?)",
                    [audit.now(), deal_id, actor, f"bid number {deal['bid_number']}, name and sector read into {draft_id}"])
        audit.record(cur, actor, SYSTEM, draft_id, "draft handoff",
                     detail=f"Linked to {deal['bid_number']}: private draft became the shared draft for the tender")
        return _draft(cur, draft_id)


def discard_draft(actor: str, draft_id: str) -> dict[str, Any]:
    with db.writing() as cur:
        _draft(cur, draft_id)
        cur.execute("DELETE FROM bid_draft WHERE draft_id = ?", [draft_id])
        cur.execute("DELETE FROM bid_presence WHERE draft_id = ?", [draft_id])
        audit.record(cur, actor, SYSTEM, draft_id, "discard draft")
    return {"discarded": draft_id}


def presence(draft_id: str, actor: str) -> list[dict[str, str]]:
    """Heartbeat. Returns who else has this draft open - presence, not co-editing."""
    with db.writing() as cur:
        now = audit.now()
        if actor:
            cur.execute("DELETE FROM bid_presence WHERE draft_id = ? AND actor = ?", [draft_id, actor])
            cur.execute("INSERT INTO bid_presence VALUES (?, ?, ?)", [draft_id, actor, now])
        rows = cur.execute("SELECT actor, last_seen FROM bid_presence WHERE draft_id = ? AND actor <> ? AND last_seen >= ?",
                           [draft_id, actor, now - timedelta(seconds=PRESENCE_SECONDS)]).fetchall()
    return [{"actor": a, "last_seen": t.isoformat()} for a, t in rows]


def submit(actor: str, draft_id: str, acknowledge_warnings: bool) -> dict[str, Any]:
    with db.writing() as cur:
        d = _draft(cur, draft_id)
        data = d["data"]
        problems = calc.validate(data)
        subject = data["project"].get("bid_number") or draft_id
        if problems["hard"]:
            audit.refuse(cur, actor, SYSTEM, subject, "submit revision",
                         "Cannot submit: required fields are missing - " + ", ".join(p["label"] for p in problems["hard"]) + ".", status=422)
        if problems["soft"] and not acknowledge_warnings:
            raise HTTPException(status_code=409, detail={
                "kind": "warnings", "soft": problems["soft"],
                "message": "Advisory fields are empty: " + ", ".join(p["label"] for p in problems["soft"]) + "."})
        number = data["project"]["bid_number"].strip()
        bid = cur.execute("SELECT bid_id, latest_revision FROM bid WHERE bid_id = ? OR bid_number = ?", [d["bid_id"], number]).fetchone()
        now = audit.now()
        if bid:
            bid_id, rev = bid[0], bid[1] + 1
            cur.execute("UPDATE bid_revision SET is_latest = false WHERE bid_id = ?", [bid_id])
            cur.execute("UPDATE bid SET latest_revision = ?, bid_name = ?, sector = ? WHERE bid_id = ?",
                        [rev, data["project"]["bid_name"], data["project"].get("sector"), bid_id])
        else:
            n = cur.execute("SELECT coalesce(max(CAST(substr(bid_id, 5) AS INTEGER)), 0) + 1 FROM bid").fetchone()[0]
            bid_id, rev = f"BID-{n:03d}", 1
            cur.execute("INSERT INTO bid VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                        [bid_id, number, d["deal_id"], data["project"]["bid_name"], data["project"].get("sector"), now, actor])
        acknowledged = ", ".join(p["label"] for p in problems["soft"])
        row = revision_row(bid_id, rev, True, now, actor, data, acknowledged)
        cur.execute(f"INSERT INTO bid_revision VALUES ({', '.join('?' for _ in row)})", list(row))
        for line in cost_line_rows(bid_id, rev, data):
            cur.execute("INSERT INTO bid_cost_line VALUES (?, ?, ?, ?, ?, ?, ?)", list(line))
        for c in data.get("competitors") or []:
            if c.get("name"):
                cur.execute("INSERT INTO bid_competitor VALUES (?, ?, ?, ?)", [bid_id, rev, c["name"], c.get("note") or ""])
        totals = calc.totals(data)
        cur.execute("INSERT INTO bid_revision_pdf VALUES (?, ?, ?)", [bid_id, rev, render_pdf(data, totals, rev, now, actor)])
        cur.execute("DELETE FROM bid_draft WHERE draft_id = ?", [draft_id])
        cur.execute("DELETE FROM bid_presence WHERE draft_id = ?", [draft_id])
        if d["deal_id"]:
            crm.client().update_deal(cur, d["deal_id"], totals["final_ex_cents"], "submitted", actor)
        audit.record(cur, actor, SYSTEM, f"{number} revision {rev}", "submit revision",
                     detail=f"{data['project']['bid_name']}: final excl. tax ${totals['final_ex_cents'] / 100:,.0f}",
                     reason=f"Submitted with advisory fields empty: {acknowledged}" if acknowledged else None)
    return {"bid_id": bid_id, "revision": rev, "bid_number": number}


# ---------------------------------------------------------------- insights --
def insights() -> dict[str, Any]:
    by_sector = db.rows("""
        SELECT r.sector, count(*) AS bids,
               count(*) FILTER (WHERE d.dealstage = 'won') AS won, count(*) FILTER (WHERE d.dealstage = 'lost') AS lost,
               count(*) FILTER (WHERE d.dealstage NOT IN ('won', 'lost')) AS open,
               avg(r.margin_bp) / 100.0 AS avg_margin_pct, avg(r.rate_per_m2_cents) / 100.0 AS avg_rate_per_m2,
               sum(r.final_ex_cents) / 100.0 AS value
        FROM bid_revision r JOIN bid b USING (bid_id) LEFT JOIN crm_deal d ON d.deal_id = b.deal_id
        WHERE r.is_latest GROUP BY 1 ORDER BY value DESC""")
    movement = db.rows("""
        SELECT l.bid_number, l.bid_name, l.revision AS revisions, f.final_ex_cents / 100.0 AS first_price,
               l.final_ex_cents / 100.0 AS latest_price, (l.final_ex_cents - f.final_ex_cents) / 100.0 AS moved,
               f.margin_bp / 100.0 AS first_margin_pct, l.margin_bp / 100.0 AS latest_margin_pct, d.dealstage AS crm_stage
        FROM bid_revision l JOIN bid_revision f ON f.bid_id = l.bid_id AND f.revision = 1
        JOIN bid b ON b.bid_id = l.bid_id LEFT JOIN crm_deal d ON d.deal_id = b.deal_id
        WHERE l.is_latest AND l.revision > 1 ORDER BY abs(l.final_ex_cents - f.final_ex_cents) DESC""")
    stage = db.rows("""SELECT dealstage, count(*) AS deals, sum(amount_cents) / 100.0 AS value FROM crm_deal GROUP BY 1""")
    won = sum(s["won"] for s in by_sector)
    lost = sum(s["lost"] for s in by_sector)
    order = {s: i for i, s in enumerate(ref.CRM_STAGES)}
    return {"by_sector": by_sector, "movement": movement, "pipeline": sorted(stage, key=lambda s: order.get(s["dealstage"], 9)),
            "totals": {"bids": sum(s["bids"] for s in by_sector), "won": won, "lost": lost,
                       "win_rate": round(won / (won + lost), 4) if won + lost else None,
                       "revisions": db.scalar("SELECT count(*) FROM bid_revision"),
                       "open_value": sum(s["value"] for s in stage if s["dealstage"] in crm.OPEN_STAGES)}}


def audit_log() -> list[dict]:
    return db.rows("""SELECT ts, actor, subject, action, outcome, detail, reason FROM audit_log
                      WHERE system = ? ORDER BY audit_id DESC LIMIT 300""", [SYSTEM])


# --------------------------------------------------------------------- PDF --
def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def render_pdf(data: dict[str, Any], totals: dict[str, int], rev: int | None, at: datetime | None, by: str | None) -> bytes:
    p, g, m = data.get("project") or {}, data.get("programme") or {}, data.get("margin") or {}
    pdf = FPDF(format="A4")
    pdf.set_creation_date(at or datetime(2026, 11, 16, 8, 30))
    pdf.set_auto_page_break(True, margin=14)
    pdf.add_page()
    pdf.set_fill_color(0, 0, 0)
    pdf.rect(0, 0, 210, 24, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_xy(10, 7)
    pdf.cell(120, 10, "Bid Summary")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(120, 7)
    pdf.cell(80, 10, f"Revision {rev}" if rev else "PREVIEW - not submitted", align="R")
    pdf.set_text_color(20, 20, 20)
    pdf.set_xy(10, 30)

    def safe(value: Any) -> str:
        return str(value if value not in (None, "") else "-").encode("latin-1", "replace").decode("latin-1")

    def dmy(value: Any) -> str:
        try:
            return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
        except ValueError:
            return "-"

    def heading(text: str) -> None:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_fill_color(74, 183, 195)
        pdf.cell(0, 6.5, "  " + text, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def pair(label: str, value: str, label2: str = "", value2: str = "") -> None:
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(38, 5.4, label)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(57, 5.4, safe(value)[:38])
        pdf.set_text_color(95, 95, 95)
        pdf.cell(38, 5.4, label2)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(57, 5.4, safe(value2)[:38] if label2 else "", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, safe(p.get("bid_name"))[:80], new_x="LMARGIN", new_y="NEXT")
    heading("Project details")
    pair("Bid number", p.get("bid_number"), "Sector", p.get("sector"))
    pair("Client", p.get("client"), "Location", p.get("location"))
    pair("Gross building area", f"{totals['gross_building_area_m2']:,} m2" if totals["gross_building_area_m2"] else "-", "Bid gate", p.get("bid_gate"))
    pair("Estimator", p.get("estimator"))
    heading("Programme")
    pair("Submission date", dmy(g.get("submission_date")), "Contract execution", dmy(g.get("contract_execution")))
    pair("Site establishment", dmy(g.get("site_establishment")), "Practical completion", dmy(g.get("practical_completion")))
    pair("Included delays", f"{g.get('included_delays')} days" if g.get("included_delays") not in (None, "") else "-")
    for title, grid, total in (("Direct costs", "direct", totals["direct_cents"]), ("Indirect costs", "indirect", totals["indirect_cents"])):
        heading(title)
        pdf.set_font("Helvetica", "", 8.5)
        for line in data.get(grid) or []:
            if not (line.get("description") or str(line.get("amount") or "").strip()):
                continue
            from src.app.calc.money import to_cents
            pdf.cell(22, 5.2, safe(line.get("cost_code")))
            pdf.cell(128, 5.2, safe(line.get("description"))[:78])
            pdf.cell(40, 5.2, _money(to_cents(line.get("amount"))), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(150, 5.6, f"Total {title.lower()}")
        pdf.cell(40, 5.6, _money(total), align="R", new_x="LMARGIN", new_y="NEXT")
    heading("Margin and risk")
    rows = [(f"Contingency ({safe(m.get('contingency_pct'))}%)", totals["contingency_cents"]), ("Escalation", totals["escalation_cents"]),
            ("Grand total (cost)", totals["grand_total_cents"]), (f"Margin ({safe(m.get('margin_pct'))}%)", totals["margin_cents"]),
            ("Final excl. tax", totals["final_ex_cents"]), ("GST", totals["gst_cents"]), ("Final incl. tax", totals["final_inc_cents"])]
    for label, cents in rows:
        pdf.set_font("Helvetica", "B" if label.startswith(("Grand", "Final")) else "", 8.8)
        pdf.cell(150, 5.4, label)
        pdf.cell(40, 5.4, _money(cents), align="R", new_x="LMARGIN", new_y="NEXT")
    heading("Competitors")
    pdf.set_font("Helvetica", "", 8.5)
    for c in data.get("competitors") or []:
        pdf.cell(0, 5.2, f"{safe(c.get('name'))} - {safe(c.get('note'))}"[:110], new_x="LMARGIN", new_y="NEXT")
    if not data.get("competitors"):
        pdf.cell(0, 5.2, "None recorded", new_x="LMARGIN", new_y="NEXT")
    heading("Benchmarking")
    b = data.get("benchmarking") or {}
    pair("Rate per m2 GBA", f"${totals['rate_per_m2_cents'] / 100:,.0f}" if totals["rate_per_m2_cents"] else "-", "Comparable", b.get("comparable"))
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(110, 110, 110)
    stamp = f"Submitted {at.strftime('%d/%m/%Y %H:%M')} by {safe(by)}. " if rev and at else "Preview only. "
    pdf.multi_cell(0, 4, stamp + "Synthetic data, generated for a demonstration. Not a real tender.")
    return bytes(pdf.output())


def revision_pdf(bid_id: str, rev: int) -> bytes:
    stored = db.raw("SELECT pdf FROM bid_revision_pdf WHERE bid_id = ? AND revision = ?", [bid_id, rev])
    if stored:
        return bytes(stored[0]["pdf"])
    # Revisions seeded by the build are rendered from their immutable snapshot on first request.
    row = db.raw("SELECT data_json, submitted_at, submitted_by FROM bid_revision WHERE bid_id = ? AND revision = ?", [bid_id, rev])
    if not row:
        raise HTTPException(status_code=404, detail="No such revision.")
    data = json.loads(row[0]["data_json"])
    return render_pdf(data, calc.totals(data), rev, row[0]["submitted_at"], row[0]["submitted_by"])


# ---------------------------------------------------------------- workbook --
FIELD_ROWS = [("project", "bid_name", "Bid Name"), ("project", "bid_number", "Bid Number"), ("project", "sector", "Sector"),
              ("project", "client", "Client"), ("project", "location", "Location"),
              ("project", "gross_building_area", "Gross Building Area (m2)"), ("project", "bid_gate", "Bid Gate"),
              ("project", "estimator", "Estimator"), ("programme", "submission_date", "Submission Date"),
              ("programme", "contract_execution", "Contract Execution"), ("programme", "site_establishment", "Site Establishment"),
              ("programme", "practical_completion", "Practical Completion Date"), ("programme", "included_delays", "Included Delays (days)"),
              ("margin", "contingency_pct", "Contingency %"), ("margin", "margin_pct", "Margin %"), ("margin", "escalation", "Escalation ($)")]
GRID_TITLES = {"direct": "DIRECT COSTS", "indirect": "INDIRECT COSTS"}


def workbook(data: dict[str, Any]) -> bytes:
    """The summary tab of the estimating workbook template: export-back writes it, import reads it."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["BID SUMMARY", "Synthetic template for a demonstration"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    for section, key, label in FIELD_ROWS:
        value = (data.get(section) or {}).get(key, "")
        ws.append([label, value])
    for grid, title in GRID_TITLES.items():
        ws.append([])
        ws.append([title])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        ws.append(["Cost code", "Description", "Amount"])
        for line in data.get(grid) or []:
            amount = line.get("amount")
            try:
                amount = float(str(amount).replace(",", "")) if str(amount or "").strip() else None
            except ValueError:
                pass
            ws.append([line.get("cost_code") or "", line.get("description") or "", amount])
        ws.append(["END"])
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 46
    ws.column_dimensions["C"].width = 16
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        return str(int(value)) if value == int(value) else f"{value:.2f}"
    return str(value).strip()


def read_workbook(content: bytes) -> dict[str, Any]:
    """Read the Summary tab into the form's shape. Returns only what was found;
    the caller shows a diff and the estimator ticks what to apply."""
    from openpyxl import load_workbook
    if len(content) > 400_000:
        raise HTTPException(status_code=413, detail="That workbook is larger than the 400 KB this import accepts.")
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=422, detail="That file could not be read as an .xlsx workbook.") from None
    if "Summary" not in wb.sheetnames:
        raise HTTPException(status_code=422, detail="No tab named Summary. Use the template from the Import dialog.")
    labels = {label.lower(): (section, key) for section, key, label in FIELD_ROWS}
    found: dict[str, Any] = {"project": {}, "programme": {}, "margin": {}}
    grid = None
    for i, row in enumerate(wb["Summary"].iter_rows(values_only=True)):
        if i > 400:
            break
        cells = [_cell(c) for c in (list(row) + [None, None, None])[:3]]
        head = cells[0].lower()
        if cells[0] in GRID_TITLES.values():
            grid = next(g for g, t in GRID_TITLES.items() if t == cells[0])
            found[grid] = []
        elif cells[0] == "END":
            grid = None
        elif grid and head != "cost code" and any(cells):
            found[grid].append({"cost_code": cells[0], "description": cells[1], "amount": cells[2]})
        elif head in labels and not grid:
            section, key = labels[head]
            found[section][key] = cells[1]
    return found
