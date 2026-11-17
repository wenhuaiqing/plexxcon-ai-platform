"""What the data agent is told about the data: every view it may read, what
each means, and the business rules a new analyst would have to be told.

It is also the page's data dictionary and the source of the questions that are
answered without a model - so there is one description of the data, used by
the prompt, the documentation and the fallback alike.
"""

from __future__ import annotations

from src.app.pipeline import reference as ref
from src.app.services import db
from src.app.services.sql_validator import ALLOWED_TABLES

VIEWS: dict[str, str] = {
    "v_project": "One row per job. job_number is the key every other view uses for a job.",
    "v_pnl_monthly": "Profit and loss by entity, month and account. amount is positive for revenue AND for costs. "
                     "account_type is revenue, other_income, cogs or expense. is_intercompany marks charges between group entities.",
    "v_balance_sheet": "Closing balance of every balance sheet account per entity at each month_end, natural sign "
                       "(assets and liabilities both positive). account_type is asset, liability or equity.",
    "v_related_party_balance": "What entity_id says it is owed by (receivable) and owes to (payable) counterparty_id at each month_end.",
    "v_gl": "General ledger lines. amount_debit_positive is signed: debits positive, credits negative. Use the P&L and "
            "balance sheet views in preference; use this for detail or a description search.",
    "v_crm_deal": "Opportunities in the CRM. dealstage is qualifying, tendering, submitted, won or lost.",
    "v_bid_revision": "Every submitted revision of every bid summary. is_latest marks the current one - filter on it "
                      "unless the question is about history. crm_stage is the opportunity's stage.",
    "v_bid_cost_line": "Cost lines of each bid revision. grid is direct or indirect.",
    "v_rate_library": "Trade Planner's shared production rates: units_per_worker_hour by trade and task.",
    "v_trade_request": "Trades and labour requests. status is draft, pending, accepted, rejected or tentative. "
                       "Only accepted requests are approved labour budget.",
    "v_trade_request_trade": "One row per trade within a request: crew, hours, working days, start and finish.",
    "v_msr_budget": "Material Supply Register budget lines. budget_* is the locked baseline; fac_* is forecast at completion; "
                    "delivered_qty is what dockets show so far.",
    "v_msr_delivery": "Pours (concrete) and bar schedules (reo). status is scheduled or delivered.",
    "v_msr_docket": "Delivery dockets: one row per truck load or bar schedule delivery.",
    "v_msr_invoice": "Supplier invoices with their docket-level reconciliation: recon_status green, amber or red; "
                     "variance_amount is invoiced minus expected.",
    "v_msr_price": "Supplier price lists with effective dates. kind is base or surcharge; waived means agreed at $0.",
}

RULES = [
    f"Today is {ref.DEMO_TODAY.isoformat()}. The ledger is closed to {ref.LEDGER_END.isoformat()}; 'latest' finance means that month end.",
    "The financial year runs 1 July to 30 June. fin_year 2027 is 1 July 2026 to 30 June 2027 (FY2026-27).",
    "Entities: CON builder, PLT plant company, PROP property trust, HOLD holding company. DIR is the directors' loan account, a related party outside the group.",
    "For a GROUP or consolidated P&L figure, exclude rows where is_intercompany is true. For one entity, include them.",
    "Profit = revenue + other_income - cogs - expense. Gross profit = revenue - cogs.",
    "register is 'concrete' (cubic metres) or 'reo' (tonnes). NEVER add quantities across the two registers; dollars may be added.",
    "Soft-deleted register rows are already excluded from the v_msr views.",
    "A bid's price is final_excl_tax unless tax is asked for. Use is_latest for 'current' figures.",
    "Win rate = won / (won + lost) over v_bid_revision where is_latest, using crm_stage.",
]

# Questions with a known-good query. They seed the page, and they are what
# answers when no model is configured.
KNOWN = [
    ("What was group revenue this financial year to date?",
     "SELECT round(sum(amount), 2) AS group_revenue_fytd FROM v_pnl_monthly WHERE fin_year = 2027 AND account_type = 'revenue' AND NOT is_intercompany",
     ["revenue", "group", "year"]),
    ("Which supplier invoices are red or amber, and by how much?",
     "SELECT job_number, supplier, invoice_no, invoiced_amount, expected_amount, variance_amount, recon_status FROM v_msr_invoice WHERE recon_status <> 'green' ORDER BY abs(variance_amount) DESC",
     ["invoice", "invoices", "red", "amber", "supplier", "reconcil"]),
    ("What is our win rate by sector?",
     "SELECT sector, count(*) FILTER (WHERE crm_stage = 'won') AS won, count(*) FILTER (WHERE crm_stage = 'lost') AS lost, round(count(*) FILTER (WHERE crm_stage = 'won') * 100.0 / nullif(count(*) FILTER (WHERE crm_stage IN ('won', 'lost')), 0), 1) AS win_rate_pct FROM v_bid_revision WHERE is_latest GROUP BY 1 ORDER BY 1",
     ["win", "rate", "sector", "bids", "won"]),
    ("How much approved labour budget does each job have?",
     "SELECT job_number, count(*) AS accepted_requests, round(sum(labour_hours), 1) AS labour_hours, round(sum(total_budget), 2) AS total_budget FROM v_trade_request WHERE status = 'accepted' GROUP BY 1 ORDER BY 1",
     ["labour", "budget", "approved", "accepted", "trade", "hours"]),
    ("Which concrete budget lines have more delivered than forecast?",
     "SELECT job_number, element, fac_qty, delivered_qty, round(delivered_qty - fac_qty, 2) AS over_by_m3 FROM v_msr_budget WHERE register = 'concrete' AND delivered_qty > fac_qty ORDER BY over_by_m3 DESC",
     ["concrete", "delivered", "forecast", "over", "budget"]),
    ("What do group entities owe each other at the latest month end?",
     "SELECT entity_id, counterparty_id, receivable, payable FROM v_related_party_balance WHERE month_end = (SELECT max(month_end) FROM v_related_party_balance) ORDER BY 1, 2",
     ["related", "party", "owe", "intercompany", "entities"]),
    ("What is the builder's cash balance by month this financial year?",
     "SELECT month_end, balance AS cash FROM v_balance_sheet WHERE entity_id = 'CON' AND account_code = '1000' AND month_end >= DATE '2026-07-01' ORDER BY 1",
     ["cash", "balance", "builder", "bank"]),
    ("Which bids changed price between their first and latest revision?",
     "SELECT l.bid_number, l.bid_name, f.final_excl_tax AS first_price, l.final_excl_tax AS latest_price, round(l.final_excl_tax - f.final_excl_tax, 2) AS moved FROM v_bid_revision l JOIN v_bid_revision f ON f.bid_id = l.bid_id AND f.revision = 1 WHERE l.is_latest AND l.revision > 1 ORDER BY abs(moved) DESC",
     ["bid", "bids", "revision", "price", "changed", "moved"]),
]


def schema() -> list[dict]:
    cols = db.rows("""SELECT table_name, column_name, data_type FROM information_schema.columns
                      WHERE table_schema = 'main' ORDER BY table_name, ordinal_position""")
    out = []
    for view in VIEWS:
        if view not in ALLOWED_TABLES:
            continue
        out.append({"view": view, "description": VIEWS[view],
                    "columns": [{"name": c["column_name"], "type": c["data_type"]} for c in cols if c["table_name"] == view]})
    return out


def prompt_block() -> str:
    parts = []
    for v in schema():
        columns = ", ".join(f"{c['name']} {c['type']}" for c in v["columns"])
        parts.append(f"- {v['view']}: {v['description']}\n    columns: {columns}")
    return "\n".join(parts)


def best_known(question: str) -> tuple[str, str] | None:
    """The catalogue question closest to this one, by shared keywords. None if nothing is close."""
    words = set("".join(ch.lower() if ch.isalnum() else " " for ch in question).split())
    scored = [(sum(1 for k in keys if any(w.startswith(k) for w in words)), q, sql) for q, sql, keys in KNOWN]
    score, q, sql = max(scored)
    return (q, sql) if score >= 2 else None
