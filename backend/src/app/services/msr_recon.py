"""Invoice reconciliation at docket level - the one definition of it.

Each invoice line is checked against the register, not against the invoice
total:

  matched     the docket is on a pour or bar schedule; expected = the docket's
              quantity at the price-list rate in force on the delivery date
  surcharge   no docket, and the description is a surcharge on the price list
              (a waived surcharge is expected at $0)
  duplicate   the docket was already billed on an earlier invoice
  unmatched   the docket number is on no delivery in the register
  unpriced    the docket is known but the price list has no rate for that day
  unlisted    a charge with no docket that the price list does not carry

  green   under 1% out and no open line
  amber   1% to 5% out, or any open line
  red     more than 5% out

A person decides what to do about an amber or red invoice; this only says
which lines to look at and why.
"""

from __future__ import annotations

from typing import Any

from src.app.calc.money import rhu
from src.app.pipeline import reference as ref

OPEN = {"duplicate", "unmatched", "unpriced", "unlisted"}


def status_for(variance_bp: int, open_lines: int) -> str:
    if variance_bp > ref.RECON_AMBER_BP:
        return "red"
    if variance_bp >= ref.RECON_GREEN_BP or open_lines > 0:
        return "amber"
    return "green"


def _rate(prices: list[tuple], supplier: str, kind: str, item: str, when: Any) -> tuple[int, bool] | None:
    for p_supplier, p_kind, p_item, rate, waived, start, end in prices:
        if p_supplier == supplier and p_kind == kind and p_item.lower() == item.lower() and start <= when and (end is None or when <= end):
            return int(rate), bool(waived)
    return None


def recompute(cur: Any, project_id: str) -> None:
    """Re-reconcile every invoice of one job. Cheap: a job has tens of invoices."""
    prices = cur.execute("""SELECT supplier, kind, item, rate_cents, waived, effective_from, effective_to
                            FROM msr_price WHERE project_id = ? AND deleted_at IS NULL
                            ORDER BY effective_from DESC""", [project_id]).fetchall()
    dockets = {}
    for docket_id, register, docket_no, delivered, item, qty in cur.execute(
            """SELECT k.docket_id, k.register, k.docket_no, k.delivered_date, k.item, k.qty_x100
               FROM msr_docket k JOIN msr_delivery v USING (delivery_id)
               WHERE k.project_id = ? AND k.deleted_at IS NULL AND v.deleted_at IS NULL""", [project_id]).fetchall():
        dockets[(register, docket_no.upper())] = (docket_id, delivered, item, int(qty))
    invoices = cur.execute("""SELECT invoice_id, register, supplier, invoice_date, total_cents FROM msr_invoice
                              WHERE project_id = ? AND deleted_at IS NULL
                              ORDER BY invoice_date, invoice_id""", [project_id]).fetchall()
    claimed: set[str] = set()
    for invoice_id, register, supplier, invoice_date, total in invoices:
        lines = cur.execute("""SELECT line_no, docket_no, description, qty_x100 FROM msr_invoice_line
                               WHERE invoice_id = ? ORDER BY line_no""", [invoice_id]).fetchall()
        expected_total, open_lines = 0, 0
        for line_no, docket_no, description, qty in lines:
            docket_id, expected = None, 0
            if (docket_no or "").strip():
                hit = dockets.get((register, docket_no.strip().upper()))
                if hit is None:
                    state = "unmatched"
                elif hit[0] in claimed:
                    docket_id, state = hit[0], "duplicate"
                else:
                    docket_id = hit[0]
                    rate = _rate(prices, supplier, "base", hit[2], hit[1])
                    if rate is None:
                        state = "unpriced"
                    else:
                        state, expected = "matched", rhu(hit[3] * rate[0], 100)
                        claimed.add(docket_id)
            else:
                rate = _rate(prices, supplier, "surcharge", (description or "").strip(), invoice_date)
                if rate is None:
                    state = "unlisted"
                else:
                    state, expected = "surcharge", 0 if rate[1] else rhu(int(qty) * rate[0], 100)
            open_lines += state in OPEN
            expected_total += expected
            cur.execute("""UPDATE msr_invoice_line SET docket_id = ?, expected_cents = ?, match_status = ?
                           WHERE invoice_id = ? AND line_no = ?""", [docket_id, expected, state, invoice_id, line_no])
        gap = abs(int(total) - expected_total)
        variance_bp = rhu(gap * 10000, expected_total) if expected_total > 0 else (10000 if gap else 0)
        cur.execute("""UPDATE msr_invoice SET expected_cents = ?, variance_bp = ?, open_lines = ?, recon_status = ?
                       WHERE invoice_id = ?""",
                    [expected_total, min(variance_bp, 99999), open_lines, status_for(variance_bp, open_lines), invoice_id])
