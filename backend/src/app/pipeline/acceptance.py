"""Acceptance checks run on every build. Each is a statement about the data a
finance manager or an estimator would hold us to, written as a query."""

from __future__ import annotations

from typing import Callable

import duckdb

from src.app.pipeline import reference as ref


def _journals_balance(con: duckdb.DuckDBPyConnection) -> tuple[bool, str]:
    n = con.execute("SELECT count(*) FROM (SELECT journal_id FROM gl_line GROUP BY 1 HAVING sum(amount_cents) <> 0)").fetchone()[0]
    return n == 0, f"{n} journals do not sum to zero"


def _balance_sheets_balance(con: duckdb.DuckDBPyConnection) -> tuple[bool, str]:
    # Double entry: for every entity at every month end, all postings to date sum to zero.
    n = con.execute("""SELECT count(*) FROM (
        SELECT entity_id, m.month_end FROM (SELECT DISTINCT last_day(posting_date) AS month_end FROM gl_line) m
        JOIN gl_line l ON l.posting_date <= m.month_end GROUP BY 1, 2 HAVING sum(amount_cents) <> 0)""").fetchone()[0]
    return n == 0, f"{n} entity month-ends out of balance"


def _ledger_window(con: duckdb.DuckDBPyConnection) -> tuple[bool, str]:
    lo, hi = con.execute("SELECT min(posting_date), max(posting_date) FROM gl_line").fetchone()
    return lo == ref.LEDGER_START and hi == ref.LEDGER_END, f"ledger runs {lo} to {hi}"


def _one_latest_revision(con: duckdb.DuckDBPyConnection) -> tuple[bool, str]:
    n = con.execute("""SELECT count(*) FROM (SELECT b.bid_id FROM bid b LEFT JOIN bid_revision r USING (bid_id)
        GROUP BY b.bid_id, b.latest_revision
        HAVING count(*) FILTER (WHERE r.is_latest) <> 1 OR max(r.revision) <> b.latest_revision)""").fetchone()[0]
    return n == 0, f"{n} bids without exactly one latest revision"


def _no_self_approval(con: duckdb.DuckDBPyConnection) -> tuple[bool, str]:
    n = con.execute("SELECT count(*) FROM tp_request WHERE reviewer IS NOT NULL AND reviewer = author").fetchone()[0]
    return n == 0, f"{n} requests reviewed by their own author"


def _reviews_carry_feedback(con: duckdb.DuckDBPyConnection) -> tuple[bool, str]:
    n = con.execute("""SELECT count(*) FROM tp_request WHERE status IN ('accepted', 'rejected', 'tentative')
                       AND (feedback IS NULL OR trim(feedback) = '')""").fetchone()[0]
    return n == 0, f"{n} decisions without feedback"


def _every_invoice_reconciled(con: duckdb.DuckDBPyConnection) -> tuple[bool, str]:
    n = con.execute("SELECT count(*) FROM msr_invoice WHERE recon_status NOT IN ('green', 'amber', 'red')").fetchone()[0]
    statuses = {r[0] for r in con.execute("SELECT DISTINCT recon_status FROM msr_invoice").fetchall()}
    return n == 0 and statuses == {"green", "amber", "red"}, f"{n} unreconciled; statuses seen {sorted(statuses)}"


def _units_never_mixed(con: duckdb.DuckDBPyConnection) -> tuple[bool, str]:
    n = con.execute("""SELECT count(*) FROM msr_budget_line
                       WHERE (register = 'concrete') <> (unit = 'm3') OR (register = 'reo') <> (unit = 't')""").fetchone()[0]
    return n == 0, f"{n} budget lines with the wrong unit for their register"


CHECKS: list[tuple[str, Callable[[duckdb.DuckDBPyConnection], tuple[bool, str]]]] = [
    ("Every journal sums to zero", _journals_balance),
    ("Every entity's balance sheet balances at every month end", _balance_sheets_balance),
    ("The ledger covers the stated window exactly", _ledger_window),
    ("Every bid has exactly one latest revision", _one_latest_revision),
    ("No trade request is reviewed by its own author", _no_self_approval),
    ("Every review decision carries feedback", _reviews_carry_feedback),
    ("Every supplier invoice has a reconciliation status, and all three occur", _every_invoice_reconciled),
    ("Concrete is in cubic metres and reinforcement in tonnes, never mixed", _units_never_mixed),
]


def run(con: duckdb.DuckDBPyConnection) -> list[tuple[str, bool, str]]:
    return [(name, *fn(con)) for name, fn in CHECKS]
