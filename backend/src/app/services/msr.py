"""Material Supply Register: concrete and reinforcement supply for a job, from
the contract budget through delivery dockets to invoice reconciliation.

Project-scoped: a job has no register until it is enrolled. Two registers per
job - concrete in cubic metres, reinforcement in tonnes - and their quantities
are never added together; only dollars are combined.

v1 boundaries, stated rather than hidden: saving is last-write-wins with no
row locking; there are no approval gates - the audit log and the
reconciliation status do that work; and nothing arrives from site apps or
supplier portals, only PDFs a person reviews.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException

from src.app.calc.money import rhu, to_cents, to_scaled
from src.app.pipeline import reference as ref
from src.app.services import audit, db, msr_recon, supplier_docs

SYSTEM = "material_register"
REGISTERS = {"concrete": {"label": "Concrete Supply", "unit": "m3", "delivery": "Pour", "docket": "Delivery docket"},
             "reo": {"label": "Reinforcement Supply", "unit": "t", "delivery": "Bar schedule", "docket": "Bar schedule"}}
SOFT_DELETE = {"budget_line": ("msr_budget_line", "line_id"), "price": ("msr_price", "price_id"),
               "delivery": ("msr_delivery", "delivery_id"), "docket": ("msr_docket", "docket_id"),
               "invoice": ("msr_invoice", "invoice_id")}
WALKTHROUGH = [
    ("portfolio", "Enrol the job", "Search by job number under Add project. A job has no register until it is enrolled."),
    ("tracking", "Set the budget", "Add budget lines by element. Budget is the locked contract baseline."),
    ("tracking", "Keep the forecast live", "Edit forecast at completion inline or measure it off a drawing. Every change needs a reason."),
    ("prices", "Load supplier rates", "Upload the quote or key the rates. Rates carry dates, so old and new prices coexist."),
    ("deliveries", "Log deliveries", "Schedule each pour or bar schedule, then attach its dockets. Delivered quantity rolls up by itself."),
    ("invoices", "Reconcile invoices", "Each invoice line is matched to a docket. Green is balanced; amber and red say which lines to look at."),
    ("audit", "Check the trail", "Every creation, edit, forecast change and delete is here, with who and when."),
]


def _enrolled(project_id: str) -> None:
    if not db.scalar("SELECT 1 FROM msr_enrolment WHERE project_id = ?", [project_id]):
        raise HTTPException(status_code=404, detail=f"Job {project_id} is not enrolled in the register.")


def _register(register: str) -> str:
    if register not in REGISTERS:
        raise HTTPException(status_code=422, detail="Register must be concrete or reo.")
    return register


# --------------------------------------------------------------- portfolio --
def _summary(project_id: str | None = None) -> list[dict]:
    where, params = ("WHERE b.project_id = ?", [project_id]) if project_id else ("", [])
    return db.rows(f"""
        WITH lines AS (
            SELECT project_id, register, count(*) AS budget_lines,
                   sum(budget_qty_x100) / 100.0 AS budget_qty, sum(budget_qty_x100 * budget_rate_cents) / 10000.0 AS budget_amount,
                   sum(fac_qty_x100) / 100.0 AS fac_qty, sum(fac_qty_x100 * fac_rate_cents) / 10000.0 AS fac_amount
            FROM msr_budget_line WHERE deleted_at IS NULL GROUP BY 1, 2),
        delivered AS (
            SELECT k.project_id, k.register, sum(k.qty_x100) / 100.0 AS delivered_qty, count(*) AS dockets
            FROM msr_docket k JOIN msr_delivery v USING (delivery_id)
            WHERE k.deleted_at IS NULL AND v.deleted_at IS NULL GROUP BY 1, 2),
        invoiced AS (
            SELECT project_id, register, sum(total_cents) / 100.0 AS invoiced_amount, count(*) AS invoices,
                   count(*) FILTER (WHERE recon_status = 'green') AS green, count(*) FILTER (WHERE recon_status = 'amber') AS amber,
                   count(*) FILTER (WHERE recon_status = 'red') AS red
            FROM msr_invoice WHERE deleted_at IS NULL GROUP BY 1, 2)
        SELECT b.project_id, b.register, b.budget_lines, b.budget_qty, b.budget_amount, b.fac_qty, b.fac_amount,
               coalesce(d.delivered_qty, 0) AS delivered_qty, coalesce(d.dockets, 0) AS dockets,
               coalesce(i.invoiced_amount, 0) AS invoiced_amount, coalesce(i.invoices, 0) AS invoices,
               coalesce(i.green, 0) AS green, coalesce(i.amber, 0) AS amber, coalesce(i.red, 0) AS red
        FROM lines b LEFT JOIN delivered d USING (project_id, register) LEFT JOIN invoiced i USING (project_id, register)
        {where} ORDER BY 1, 2""", params)


def portfolio() -> dict[str, Any]:
    projects = db.rows("""SELECT p.project_id, p.name, p.client, p.sector, p.status, e.enrolled_at, e.enrolled_by
                          FROM msr_enrolment e JOIN project p USING (project_id) ORDER BY p.project_id""")
    summary = _summary()
    inbox = {r["project_id"]: r["n"] for r in db.rows(
        "SELECT project_id, count(*) AS n FROM msr_document WHERE status = 'inbox' GROUP BY 1")}
    for p in projects:
        p["inbox"] = inbox.get(p["project_id"], 0)
    return {
        "projects": projects, "registers": REGISTERS,
        "summary": {reg: [{**s, **next(p for p in projects if p["project_id"] == s["project_id"])}
                          for s in summary if s["register"] == reg] for reg in REGISTERS},
        "walkthrough": [{"tab": t, "title": title, "text": text} for t, title, text in WALKTHROUGH],
    }


def search_jobs(q: str) -> list[dict]:
    like = f"%{q.strip()}%"
    return db.rows("""SELECT p.project_id, p.name, p.client, p.status,
                             (p.project_id IN (SELECT project_id FROM msr_enrolment)) AS enrolled
                      FROM project p WHERE p.project_id LIKE ? OR lower(p.name) LIKE lower(?) ORDER BY p.project_id LIMIT 8""", [like, like])


def enrol(actor: str, project_id: str) -> dict[str, Any]:
    with db.writing() as cur:
        if not cur.execute("SELECT 1 FROM project WHERE project_id = ?", [project_id]).fetchone():
            raise HTTPException(status_code=404, detail=f"No job numbered {project_id}.")
        if cur.execute("SELECT 1 FROM msr_enrolment WHERE project_id = ?", [project_id]).fetchone():
            audit.refuse(cur, actor, SYSTEM, f"Job {project_id}", "enrol project", f"Job {project_id} is already enrolled.", project_id=project_id)
        cur.execute("INSERT INTO msr_enrolment VALUES (?, ?, ?)", [project_id, audit.now(), actor])
        audit.record(cur, actor, SYSTEM, f"Job {project_id}", "enrol project", project_id=project_id,
                     detail="Concrete and reinforcement registers opened")
    return {"project_id": project_id}


# --------------------------------------------------------------- workspace --
def workspace(project_id: str, register: str) -> dict[str, Any]:
    _enrolled(project_id)
    _register(register)
    project = db.rows("SELECT project_id, name, client, sector, status, start_date, end_date FROM project WHERE project_id = ?", [project_id])[0]
    args = [project_id, register]
    lines = db.rows("""
        SELECT b.line_id, b.element, b.sub_element, b.unit, b.budget_qty_x100 / 100.0 AS budget_qty, b.budget_rate_cents / 100.0 AS budget_rate,
               b.budget_qty_x100 * b.budget_rate_cents / 10000.0 AS budget_amount, b.fac_qty_x100 / 100.0 AS fac_qty,
               b.fac_rate_cents / 100.0 AS fac_rate, b.fac_qty_x100 * b.fac_rate_cents / 10000.0 AS fac_amount,
               coalesce(d.qty, 0) / 100.0 AS delivered_qty, coalesce(d.dockets, 0) AS dockets, b.deleted_at
        FROM msr_budget_line b LEFT JOIN (
            SELECT v.line_id, sum(k.qty_x100) AS qty, count(*) AS dockets FROM msr_docket k JOIN msr_delivery v USING (delivery_id)
            WHERE k.deleted_at IS NULL AND v.deleted_at IS NULL GROUP BY 1) d USING (line_id)
        WHERE b.project_id = ? AND b.register = ? ORDER BY b.deleted_at IS NOT NULL, b.line_id""", args)
    prices = db.rows("""SELECT price_id, supplier, kind, item, unit, rate_cents / 100.0 AS rate, waived, effective_from, effective_to,
                               source_doc_id, deleted_at,
                               (effective_from <= ? AND (effective_to IS NULL OR effective_to >= ?)) AS current
                        FROM msr_price WHERE project_id = ? AND register = ?
                        ORDER BY deleted_at IS NOT NULL, kind, item, effective_from""", [ref.DEMO_TODAY, ref.DEMO_TODAY, *args])
    deliveries = db.rows("""
        SELECT v.delivery_id, v.line_id, b.element, v.description, v.supplier, v.item, v.scheduled_date,
               v.planned_qty_x100 / 100.0 AS planned_qty, coalesce(sum(k.qty_x100), 0) / 100.0 AS delivered_qty,
               count(k.docket_id) AS dockets, string_agg(k.docket_no, ', ' ORDER BY k.docket_no) AS docket_nos, v.deleted_at
        FROM msr_delivery v LEFT JOIN msr_docket k ON k.delivery_id = v.delivery_id AND k.deleted_at IS NULL
        LEFT JOIN msr_budget_line b ON b.line_id = v.line_id
        WHERE v.project_id = ? AND v.register = ?
        GROUP BY ALL ORDER BY v.deleted_at NULLS FIRST, v.scheduled_date DESC""", args)
    for d in deliveries:
        d["status"] = ("delivered" if d["dockets"] else
                       "awaiting docket" if d["scheduled_date"] < ref.DEMO_TODAY.isoformat() else "scheduled")
    invoices = db.rows("""SELECT invoice_id, supplier, invoice_no, invoice_date, total_cents / 100.0 AS total,
                                 expected_cents / 100.0 AS expected, (total_cents - expected_cents) / 100.0 AS variance,
                                 variance_bp / 100.0 AS variance_pct, open_lines, recon_status, source_doc_id, deleted_at,
                                 (SELECT count(*) FROM msr_invoice_line l WHERE l.invoice_id = i.invoice_id) AS lines
                          FROM msr_invoice i WHERE project_id = ? AND register = ?
                          ORDER BY deleted_at IS NOT NULL, invoice_date DESC, invoice_id DESC""", args)
    log = db.rows("""SELECT ts, actor, subject, action, outcome, detail, reason FROM audit_log
                     WHERE system = ? AND project_id = ? ORDER BY audit_id DESC LIMIT 200""", [SYSTEM, project_id])
    inbox = db.rows("""SELECT doc_id, register, kind, supplier, filename, status, received_at, received_by FROM msr_document
                       WHERE project_id = ? AND status = 'inbox' ORDER BY doc_id""", [project_id])
    live = [ln for ln in lines if not ln["deleted_at"]]
    live_inv = [i for i in invoices if not i["deleted_at"]]
    delivered_value = db.scalar("""
        SELECT coalesce(sum(k.qty_x100 * b.fac_rate_cents), 0) / 10000.0 FROM msr_docket k JOIN msr_delivery v USING (delivery_id)
        JOIN msr_budget_line b ON b.line_id = v.line_id
        WHERE k.project_id = ? AND k.register = ? AND k.deleted_at IS NULL AND v.deleted_at IS NULL""", args)
    budget, fac = sum(ln["budget_amount"] for ln in live), sum(ln["fac_amount"] for ln in live)
    invoiced = sum(i["total"] for i in live_inv)
    combined = _summary(project_id)
    weeks = db.rows("""
        SELECT date_trunc('week', v.scheduled_date)::DATE AS week, sum(v.planned_qty_x100) / 100.0 AS planned,
               coalesce(sum(k.qty), 0) / 100.0 AS delivered, count(*) AS events
        FROM msr_delivery v LEFT JOIN (SELECT delivery_id, sum(qty_x100) AS qty FROM msr_docket WHERE deleted_at IS NULL GROUP BY 1) k
             USING (delivery_id)
        WHERE v.project_id = ? AND v.register = ? AND v.deleted_at IS NULL GROUP BY 1 ORDER BY 1""", args)
    return {
        "project": project, "register": register, "meta": REGISTERS[register], "registers": REGISTERS,
        "today": ref.DEMO_TODAY.isoformat(),
        "dashboard": {
            "budget": budget, "fac": fac, "fac_vs_budget": fac - budget, "invoiced": invoiced,
            "delivered_value": delivered_value, "delivered_not_invoiced": max(delivered_value - invoiced, 0),
            "budget_qty": sum(ln["budget_qty"] for ln in live), "fac_qty": sum(ln["fac_qty"] for ln in live),
            "delivered_qty": sum(ln["delivered_qty"] for ln in live),
            "recon": {s: sum(1 for i in live_inv if i["recon_status"] == s) for s in ("green", "amber", "red")},
            "over_forecast": [ln["element"] for ln in live if ln["delivered_qty"] > ln["fac_qty"]],
            "awaiting_docket": sum(1 for d in deliveries if d["status"] == "awaiting docket" and not d["deleted_at"]),
            "weeks": weeks,
            "combined": {"budget": sum(c["budget_amount"] for c in combined), "fac": sum(c["fac_amount"] for c in combined),
                         "invoiced": sum(c["invoiced_amount"] for c in combined)},
        },
        "tracking": lines, "prices": prices, "deliveries": deliveries, "invoices": invoices, "audit": log, "inbox": inbox,
        "suppliers": sorted({p["supplier"] for p in prices}), "items": sorted({p["item"] for p in prices if p["kind"] == "base"}),
        "walkthrough": [{"tab": t, "title": title, "text": text} for t, title, text in WALKTHROUGH],
    }


def invoice_detail(invoice_id: str) -> dict[str, Any]:
    head = db.rows("""SELECT invoice_id, project_id, register, supplier, invoice_no, invoice_date, total_cents / 100.0 AS total,
                             expected_cents / 100.0 AS expected, variance_bp / 100.0 AS variance_pct, open_lines, recon_status
                      FROM msr_invoice WHERE invoice_id = ?""", [invoice_id])
    if not head:
        raise HTTPException(status_code=404, detail="No such invoice.")
    lines = db.rows("""SELECT l.line_no, l.docket_no, l.description, l.qty_x100 / 100.0 AS qty, l.rate_cents / 100.0 AS rate,
                              l.amount_cents / 100.0 AS amount, l.expected_cents / 100.0 AS expected, l.match_status,
                              v.description AS delivery, k.delivered_date
                       FROM msr_invoice_line l LEFT JOIN msr_docket k ON k.docket_id = l.docket_id
                       LEFT JOIN msr_delivery v ON v.delivery_id = k.delivery_id
                       WHERE l.invoice_id = ? ORDER BY l.line_no""", [invoice_id])
    return {**head[0], "lines": lines}


# ------------------------------------------------------------------ writes --
def _id(cur: Any, table: str, column: str, prefix: str, width: int) -> str:
    n = cur.execute(f"SELECT coalesce(max(CAST(substr({column}, {len(prefix) + 2}) AS INTEGER)), 0) + 1 FROM {table}").fetchone()[0]
    return f"{prefix}-{n:0{width}d}"


def _positive(cur: Any, actor: str, project_id: str, subject: str, action: str, value: Any, scale: int, what: str) -> int:
    try:
        number = to_cents(value) if scale == 0 else to_scaled(value, scale)
    except ValueError:
        number = 0
    if number <= 0:
        audit.refuse(cur, actor, SYSTEM, subject, action, f"{what} must be a number above zero.", project_id=project_id, status=422)
    return number


def add_budget_line(actor: str, project_id: str, register: str, element: str, sub_element: str, qty: Any, rate: Any) -> dict:
    _enrolled(project_id)
    _register(register)
    with db.writing() as cur:
        action = "add budget line"
        if not element.strip():
            audit.refuse(cur, actor, SYSTEM, "new line", action, "Give the element a name.", project_id=project_id, status=422)
        q = _positive(cur, actor, project_id, element, action, qty, 100, "Quantity")
        r = _positive(cur, actor, project_id, element, action, rate, 0, "Rate")
        line_id = _id(cur, "msr_budget_line", "line_id", "BL", 4)
        now = audit.now()
        cur.execute("INSERT INTO msr_budget_line VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                    [line_id, project_id, register, element.strip()[:60], sub_element.strip()[:80], REGISTERS[register]["unit"],
                     q, r, q, r, now, actor])
        audit.record(cur, actor, SYSTEM, f"{element.strip()} ({line_id})", action, project_id=project_id,
                     detail=f"{REGISTERS[register]['label']}: {q / 100:g} {REGISTERS[register]['unit']} at ${r / 100:,.2f}; forecast starts equal to budget")
    return {"line_id": line_id}


def set_forecast(actor: str, line_id: str, fac_qty: Any, fac_rate: Any, reason: str) -> dict:
    with db.writing() as cur:
        row = cur.execute("""SELECT project_id, element, unit, fac_qty_x100, fac_rate_cents FROM msr_budget_line
                             WHERE line_id = ? AND deleted_at IS NULL""", [line_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No such budget line.")
        project_id, element, unit, old_q, old_r = row
        action, subject = "change forecast", f"{element} ({line_id})"
        if not reason.strip():
            audit.refuse(cur, actor, SYSTEM, subject, action, "A forecast change needs a reason.", project_id=project_id, status=422)
        q = _positive(cur, actor, project_id, subject, action, fac_qty, 100, "Forecast quantity")
        r = _positive(cur, actor, project_id, subject, action, fac_rate, 0, "Forecast rate")
        cur.execute("UPDATE msr_budget_line SET fac_qty_x100 = ?, fac_rate_cents = ? WHERE line_id = ?", [q, r, line_id])
        audit.record(cur, actor, SYSTEM, subject, action, project_id=project_id, reason=reason.strip()[:300],
                     detail=f"{old_q / 100:g} {unit} at ${old_r / 100:,.2f} to {q / 100:g} {unit} at ${r / 100:,.2f}")
    return {"line_id": line_id}


def add_price(actor: str, project_id: str, register: str, supplier: str, kind: str, item: str, unit: str, rate: Any,
              waived: bool, effective_from: str, source_doc_id: str | None = None, cur: Any = None) -> dict:
    _enrolled(project_id)
    _register(register)

    def run(c: Any) -> dict:
        action = "add rate"
        try:
            start = date.fromisoformat(effective_from)
        except ValueError:
            audit.refuse(c, actor, SYSTEM, item, action, "Effective-from must be a date.", project_id=project_id, status=422)
        if kind not in ("base", "surcharge") or not supplier.strip() or not item.strip():
            audit.refuse(c, actor, SYSTEM, item or "rate", action, "A rate needs a supplier, an item and a kind.", project_id=project_id, status=422)
        try:
            cents = 0 if waived else to_cents(rate)
        except ValueError:
            cents = -1
        if cents < 0 or (cents == 0 and not waived):
            audit.refuse(c, actor, SYSTEM, item, action, "Rate must be above zero, or the charge marked as waived.", project_id=project_id, status=422)
        # The new rate takes over from its start date: close the one it replaces the day before.
        c.execute("""UPDATE msr_price SET effective_to = ? WHERE project_id = ? AND register = ? AND supplier = ? AND kind = ?
                     AND lower(item) = lower(?) AND deleted_at IS NULL AND effective_from < ?
                     AND (effective_to IS NULL OR effective_to >= ?)""",
                  [start - timedelta(days=1), project_id, register, supplier.strip(), kind, item.strip(), start, start])
        price_id = _id(c, "msr_price", "price_id", "PR", 4)
        c.execute("INSERT INTO msr_price VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL)",
                  [price_id, project_id, register, supplier.strip()[:60], kind, item.strip()[:60], unit.strip()[:20] or REGISTERS[register]["unit"],
                   cents, bool(waived), start, source_doc_id, audit.now(), actor])
        audit.record(c, actor, SYSTEM, f"{item.strip()} ({price_id})", action, project_id=project_id,
                     detail=f"{supplier.strip()}: " + ("waived at $0" if waived else f"${cents / 100:,.2f} {unit}") + f" from {start.strftime('%d/%m/%Y')}")
        return {"price_id": price_id}

    if cur is not None:
        return run(cur)
    with db.writing() as c:
        out = run(c)
        msr_recon.recompute(c, project_id)
        return out


def schedule_delivery(actor: str, project_id: str, register: str, line_id: str, description: str, supplier: str, item: str,
                      scheduled_date: str, planned_qty: Any) -> dict:
    _enrolled(project_id)
    _register(register)
    with db.writing() as cur:
        action = "schedule delivery"
        line = cur.execute("SELECT element FROM msr_budget_line WHERE line_id = ? AND project_id = ? AND register = ? AND deleted_at IS NULL",
                           [line_id, project_id, register]).fetchone()
        if not line:
            audit.refuse(cur, actor, SYSTEM, description or "delivery", action,
                         "Link the delivery to a budget line of this register, so its quantity rolls up.", project_id=project_id, status=422)
        try:
            when = date.fromisoformat(scheduled_date)
        except ValueError:
            audit.refuse(cur, actor, SYSTEM, description or "delivery", action, "Scheduled date must be a date.", project_id=project_id, status=422)
        q = _positive(cur, actor, project_id, description or "delivery", action, planned_qty, 100, "Planned quantity")
        delivery_id = _id(cur, "msr_delivery", "delivery_id", "DL", 4)
        label = description.strip()[:80] or f"{line[0]} - {REGISTERS[register]['delivery'].lower()}"
        cur.execute("INSERT INTO msr_delivery VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                    [delivery_id, project_id, register, line_id, label, supplier.strip()[:60], item.strip()[:60], when, q, audit.now(), actor])
        audit.record(cur, actor, SYSTEM, f"{label} ({delivery_id})", action, project_id=project_id,
                     detail=f"{q / 100:g} {REGISTERS[register]['unit']} of {item} on {when.strftime('%d/%m/%Y')}")
    return {"delivery_id": delivery_id}


def soft_delete(actor: str, kind: str, row_id: str, restore: bool) -> dict:
    if kind not in SOFT_DELETE:
        raise HTTPException(status_code=422, detail="Unknown record type.")
    table, column = SOFT_DELETE[kind]
    with db.writing() as cur:
        row = cur.execute(f"SELECT project_id, deleted_at FROM {table} WHERE {column} = ?", [row_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No such record.")
        project_id, deleted_at = row
        action = f"{'restore' if restore else 'delete'} {kind.replace('_', ' ')}"
        if restore == (deleted_at is None):
            raise HTTPException(status_code=409, detail="Nothing to do: it is already " + ("live." if restore else "deleted."))
        if not restore and kind == "budget_line" and cur.execute(
                "SELECT 1 FROM msr_delivery WHERE line_id = ? AND deleted_at IS NULL LIMIT 1", [row_id]).fetchone():
            audit.refuse(cur, actor, SYSTEM, row_id, action,
                         "This budget line has deliveries against it. Delete or move those first.", project_id=project_id)
        if not restore and kind == "delivery" and cur.execute(
                "SELECT 1 FROM msr_docket WHERE delivery_id = ? AND deleted_at IS NULL LIMIT 1", [row_id]).fetchone():
            audit.refuse(cur, actor, SYSTEM, row_id, action,
                         "This delivery has dockets recorded. Delete the dockets first.", project_id=project_id)
        cur.execute(f"UPDATE {table} SET deleted_at = ?, deleted_by = ? WHERE {column} = ?",
                    [None if restore else audit.now(), None if restore else actor, row_id])
        audit.record(cur, actor, SYSTEM, row_id, action, project_id=project_id,
                     detail="Soft delete undone" if restore else "Soft delete: kept in the database, hidden from totals")
        msr_recon.recompute(cur, project_id)
    return {"kind": kind, "id": row_id, "deleted": not restore}


# --------------------------------------------------------------- documents --
def document_pdf(doc_id: str) -> bytes:
    found = db.raw("SELECT pdf FROM msr_document_blob WHERE doc_id = ?", [doc_id])
    if not found:
        raise HTTPException(status_code=404, detail="No such document.")
    return bytes(found[0]["pdf"])


def invoice_pdf(invoice_id: str) -> bytes:
    """The source PDF of an invoice. Invoices seeded by the build were never
    uploaded, so theirs is rendered from the stored lines in the supplier's layout."""
    head = db.raw("SELECT project_id, supplier, invoice_no, invoice_date, source_doc_id FROM msr_invoice WHERE invoice_id = ?", [invoice_id])
    if not head:
        raise HTTPException(status_code=404, detail="No such invoice.")
    h = head[0]
    if h["source_doc_id"]:
        return document_pdf(h["source_doc_id"])
    lines = db.raw("SELECT docket_no, description, qty_x100, rate_cents, amount_cents FROM msr_invoice_line WHERE invoice_id = ? ORDER BY line_no",
                   [invoice_id])
    return supplier_docs.render("invoice", h["supplier"], {
        "invoice_no": h["invoice_no"], "date": h["invoice_date"].isoformat(), "job": h["project_id"],
        "lines": [[ln["docket_no"] or "", ln["description"], int(ln["qty_x100"]), int(ln["rate_cents"]), int(ln["amount_cents"])] for ln in lines]})


def parse_document(doc_id: str) -> dict[str, Any]:
    doc = db.rows("SELECT doc_id, project_id, register, kind, supplier, filename, status FROM msr_document WHERE doc_id = ?", [doc_id])
    if not doc:
        raise HTTPException(status_code=404, detail="No such document.")
    d = doc[0]
    proposal = supplier_docs.parse(document_pdf(doc_id), d["kind"])
    kind = proposal["kind"]
    project_id, register = d["project_id"], d["register"]
    if kind == "docket":
        # Offer the pours this docket could belong to: same register, no docket yet, nearest date first.
        when = proposal["fields"].get("date") or ref.DEMO_TODAY.isoformat()
        proposal["candidates"] = db.rows("""
            SELECT v.delivery_id, v.description, v.scheduled_date, v.item, v.planned_qty_x100 / 100.0 AS planned_qty,
                   (SELECT count(*) FROM msr_docket k WHERE k.delivery_id = v.delivery_id AND k.deleted_at IS NULL) AS dockets
            FROM msr_delivery v WHERE v.project_id = ? AND v.register = ? AND v.deleted_at IS NULL
            ORDER BY abs(datediff('day', v.scheduled_date, CAST(? AS DATE))), v.delivery_id LIMIT 6""", [project_id, register, when])
        proposal["suggested_delivery_id"] = proposal["candidates"][0]["delivery_id"] if proposal["candidates"] else None
    if kind == "invoice":
        # Pre-match each line by docket number; the person confirms or corrects.
        known = {r["docket_no"].upper(): r for r in db.rows(
            """SELECT k.docket_no, k.qty_x100 / 100.0 AS qty, v.description AS delivery, k.delivered_date
               FROM msr_docket k JOIN msr_delivery v USING (delivery_id)
               WHERE k.project_id = ? AND k.register = ? AND k.deleted_at IS NULL AND v.deleted_at IS NULL""", [project_id, register])}
        for line in proposal.get("lines") or []:
            hit = known.get((line.get("docket_no") or "").upper())
            line["prematch"] = ({"delivery": hit["delivery"], "qty": hit["qty"], "delivered_date": hit["delivered_date"]} if hit else None)
    return {**proposal, "document": d, "register_meta": REGISTERS[register]}


def commit_document(actor: str, doc_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Nothing a parser read reaches the register until a person confirms it here."""
    with db.writing() as cur:
        row = cur.execute("SELECT project_id, register, kind, supplier, status FROM msr_document WHERE doc_id = ?", [doc_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No such document.")
        project_id, register, _hint, _supplier, status = row
        kind = body.get("kind") or _hint
        fields = body.get("fields") or {}
        supplier = (body.get("supplier") or _supplier or "").strip()
        subject, action = f"{doc_id} ({kind})", f"confirm {kind}"
        if status != "inbox":
            audit.refuse(cur, actor, SYSTEM, subject, action, "This document has already been confirmed.", project_id=project_id)
        unit = REGISTERS[register]["unit"]
        now = audit.now()
        if kind == "docket":
            docket_no = str(fields.get("docket_no") or "").strip()
            delivery = cur.execute("""SELECT delivery_id, item FROM msr_delivery WHERE delivery_id = ? AND project_id = ? AND register = ?
                                      AND deleted_at IS NULL""", [body.get("delivery_id"), project_id, register]).fetchone()
            if not docket_no:
                audit.refuse(cur, actor, SYSTEM, subject, action, "A docket needs its docket number.", project_id=project_id, status=422)
            if not delivery:
                audit.refuse(cur, actor, SYSTEM, subject, action,
                             "Choose the pour or bar schedule this docket belongs to.", project_id=project_id, status=422)
            if cur.execute("SELECT 1 FROM msr_docket WHERE project_id = ? AND upper(docket_no) = upper(?) AND deleted_at IS NULL",
                           [project_id, docket_no]).fetchone():
                audit.refuse(cur, actor, SYSTEM, subject, action,
                             f"Docket {docket_no} is already on this job's register. Recording it twice would double the delivered quantity.",
                             project_id=project_id)
            try:
                when = date.fromisoformat(str(fields.get("date") or ""))
            except ValueError:
                audit.refuse(cur, actor, SYSTEM, subject, action, "The delivery date is missing or not a date.", project_id=project_id, status=422)
            qty = _positive(cur, actor, project_id, subject, action, fields.get("qty"), 100, "Quantity")
            docket_id = _id(cur, "msr_docket", "docket_id", "DK", 5)
            cur.execute("INSERT INTO msr_docket VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                        [docket_id, delivery[0], project_id, register, docket_no, when, str(fields.get("item") or delivery[1])[:60],
                         qty, doc_id, now, actor])
            ref_id, detail = docket_id, f"Docket {docket_no}: {qty / 100:g} {unit} to {delivery[0]}"
        elif kind == "invoice":
            invoice_no = str(fields.get("invoice_no") or "").strip()
            lines = body.get("lines") or []
            if not invoice_no or not lines:
                audit.refuse(cur, actor, SYSTEM, subject, action, "An invoice needs its number and at least one line.", project_id=project_id, status=422)
            if cur.execute("SELECT 1 FROM msr_invoice WHERE project_id = ? AND upper(invoice_no) = upper(?) AND deleted_at IS NULL",
                           [project_id, invoice_no]).fetchone():
                audit.refuse(cur, actor, SYSTEM, subject, action, f"Invoice {invoice_no} is already on this job's register.", project_id=project_id)
            try:
                when = date.fromisoformat(str(fields.get("date") or ""))
            except ValueError:
                audit.refuse(cur, actor, SYSTEM, subject, action, "The invoice date is missing or not a date.", project_id=project_id, status=422)
            parsed = []
            for i, ln in enumerate(lines[:200], start=1):
                try:
                    q, r = to_scaled(ln.get("qty"), 100), to_cents(ln.get("rate"))
                    amount = to_cents(ln.get("amount")) if str(ln.get("amount") or "").strip() else rhu(q * r, 100)
                except ValueError:
                    audit.refuse(cur, actor, SYSTEM, subject, action, f"Line {i} has a quantity, rate or amount that is not a number.",
                                 project_id=project_id, status=422)
                parsed.append((i, str(ln.get("docket_no") or "").strip()[:40], str(ln.get("description") or "")[:120], q, r, amount))
            invoice_id = _id(cur, "msr_invoice", "invoice_id", "INV", 4)
            cur.execute("INSERT INTO msr_invoice VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, '', ?, ?, NULL, NULL)",
                        [invoice_id, project_id, register, supplier[:60], invoice_no[:60], when, sum(p[5] for p in parsed), doc_id, now, actor])
            for p in parsed:
                cur.execute("INSERT INTO msr_invoice_line VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, '')", [invoice_id, *p])
            ref_id, detail = invoice_id, f"Invoice {invoice_no}: {len(parsed)} lines, ${sum(p[5] for p in parsed) / 100:,.2f}"
        elif kind == "quote":
            rates = body.get("rates") or []
            start = str(fields.get("effective_from") or "")
            if not rates:
                audit.refuse(cur, actor, SYSTEM, subject, action, "A quote needs at least one rate.", project_id=project_id, status=422)
            for r in rates[:60]:
                add_price(actor, project_id, register, supplier, r.get("kind") or "base", str(r.get("item") or ""),
                          str(r.get("unit") or unit), r.get("rate"), bool(r.get("waived")), start, doc_id, cur=cur)
            ref_id, detail = doc_id, f"{len(rates)} rates effective {start}"
        else:
            raise HTTPException(status_code=422, detail="Unknown document type.")
        cur.execute("UPDATE msr_document SET status = 'committed', committed_ref = ?, kind = ?, supplier = ? WHERE doc_id = ?",
                    [ref_id, kind, supplier[:60], doc_id])
        audit.record(cur, actor, SYSTEM, subject, action, project_id=project_id,
                     detail=detail + f" (read by {body.get('parser') or 'hand'}, confirmed by a person)")
        msr_recon.recompute(cur, project_id)
    return {"doc_id": doc_id, "kind": kind, "ref": ref_id}


def upload(actor: str, project_id: str, register: str, filename: str, content: bytes) -> dict[str, Any]:
    _enrolled(project_id)
    _register(register)
    if len(content) > 1_500_000:
        raise HTTPException(status_code=413, detail="That file is larger than the 1.5 MB this demo accepts.")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="Only PDF files are accepted.")
    proposal = supplier_docs.parse(content)
    with db.writing() as cur:
        doc_id = _id(cur, "msr_document", "doc_id", "DOC", 4)
        safe = "".join(ch for ch in filename if ch.isalnum() or ch in "-_. ")[:80] or "upload.pdf"
        cur.execute("INSERT INTO msr_document VALUES (?, ?, ?, ?, ?, ?, 'inbox', ?, ?, NULL)",
                    [doc_id, project_id, register, proposal["kind"], proposal.get("supplier") or "", safe, audit.now(), actor])
        cur.execute("INSERT INTO msr_document_blob VALUES (?, ?)", [doc_id, content])
        audit.record(cur, actor, SYSTEM, doc_id, "upload document", project_id=project_id, detail=safe)
    return {"doc_id": doc_id}
