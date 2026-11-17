"""Finance reporting: profit and loss, balance sheet, related-party balances.

Read-only, straight from the general ledger. Three rules:

- Every figure is a sum of ledger lines; nothing is typed in.
- The group view eliminates balances and charges between group entities. If
  the two sides of an intercompany balance disagree, the difference is shown
  as its own line - never spread or hidden - so the statement still adds up
  and the reader is sent to the Related Party Balance page.
- The mirror check there finds what does not agree and says why, from the
  transactions on both ledgers.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from src.app.pipeline import reference as ref
from src.app.services import db

GROUP = "GROUP"
PNL_SECTIONS = ["Revenue", "Cost of sales", "Overheads", "Other income"]
BS_SECTIONS = ["Current assets", "Non-current assets", "Current liabilities", "Non-current liabilities", "Equity"]


def _entities() -> list[dict]:
    return db.raw("SELECT entity_id, name, description, is_group FROM entity ORDER BY is_group DESC, entity_id")


def _group_ids() -> list[str]:
    return [e["entity_id"] for e in _entities() if e["is_group"]]


def fy_of(d: date) -> int:
    return d.year + 1 if d.month >= ref.FY_START_MONTH else d.year


def fy_start(fy: int) -> date:
    return date(fy - 1, ref.FY_START_MONTH, 1)


def month_ends() -> list[date]:
    return [r["m"] for r in db.raw("SELECT DISTINCT last_day(posting_date) AS m FROM gl_line ORDER BY 1")]


def options() -> dict[str, Any]:
    ends = month_ends()
    return {
        "entities": [{"entity_id": GROUP, "name": "Group (consolidated)"}]
                    + [{"entity_id": e["entity_id"], "name": e["name"]} for e in _entities() if e["is_group"]],
        "fin_years": sorted({fy_of(m) for m in ends}, reverse=True),
        "month_ends": [m.isoformat() for m in reversed(ends)],
        "latest": ends[-1].isoformat(),
        "ledger_from": ends[0].replace(day=1).isoformat(),
    }


def _scope(entity: str) -> tuple[str, list[Any]]:
    if entity == GROUP:
        ids = _group_ids()
        return f"l.entity_id IN ({', '.join('?' for _ in ids)})", ids
    return "l.entity_id = ?", [entity]


# -------------------------------------------------------------------- P&L --
def pnl(entity: str = GROUP, fin_year: int | None = None) -> dict[str, Any]:
    ends = month_ends()
    fin_year = fin_year or fy_of(ends[-1])
    start = fy_start(fin_year)
    periods = [m for m in ends if fy_of(m) == fin_year]
    if not periods:
        return {"entity": entity, "fin_year": fin_year, "periods": [], "sections": [], "totals": {}}
    last = periods[-1]
    prior_start, prior_last = fy_start(fin_year - 1), date(last.year - 1, last.month, 28) + timedelta(days=4)
    prior_last = prior_last - timedelta(days=prior_last.day)   # same month end a year earlier
    where, params = _scope(entity)
    group_ids = _group_ids()
    marks = ", ".join("?" for _ in group_ids)
    rows = db.raw(f"""
        SELECT a.section, a.account_code, a.name, a.type, a.sort_order, last_day(l.posting_date) AS month_end,
               (l.counterparty_id IN ({marks})) AS intercompany,
               sum(CASE WHEN a.type IN ('revenue', 'other_income') THEN -l.amount_cents ELSE l.amount_cents END) AS cents
        FROM gl_line l JOIN gl_account a USING (account_code)
        WHERE {where} AND a.type IN ('revenue', 'other_income', 'cogs', 'expense') AND l.posting_date >= ? AND l.posting_date <= ?
        GROUP BY ALL ORDER BY a.sort_order""", [*group_ids, *params, prior_start, last])

    consolidated = entity == GROUP
    eliminated = {"revenue": 0, "costs": 0}
    accounts: dict[str, dict[str, Any]] = {}
    for r in rows:
        current = fy_of(r["month_end"]) == fin_year
        in_prior_ytd = (not current) and r["month_end"] <= prior_last
        if not current and not in_prior_ytd:
            continue
        if consolidated and r["intercompany"]:
            if current:
                eliminated["revenue" if r["type"] in ("revenue", "other_income") else "costs"] += r["cents"]
            continue
        acc = accounts.setdefault(r["account_code"], {
            "account_code": r["account_code"], "name": r["name"], "section": r["section"], "type": r["type"],
            "months": {m.isoformat(): 0 for m in periods}, "ytd": 0, "prior_ytd": 0})
        if current:
            acc["months"][r["month_end"].isoformat()] += r["cents"]
            acc["ytd"] += r["cents"]
        else:
            acc["prior_ytd"] += r["cents"]

    def money(c: int) -> float:
        return round(c / 100, 2)

    sections = []
    sums: dict[str, dict[str, Any]] = {}
    for name in PNL_SECTIONS:
        lines = [a for a in accounts.values() if a["section"] == name and (a["ytd"] or a["prior_ytd"])]
        total = {"months": {m.isoformat(): sum(a["months"][m.isoformat()] for a in lines) for m in periods},
                 "ytd": sum(a["ytd"] for a in lines), "prior_ytd": sum(a["prior_ytd"] for a in lines)}
        sums[name] = total
        sections.append({"section": name,
                         "lines": [{**a, "months": [money(a["months"][m.isoformat()]) for m in periods],
                                    "ytd": money(a["ytd"]), "prior_ytd": money(a["prior_ytd"])} for a in lines],
                         "total": {"months": [money(total["months"][m.isoformat()]) for m in periods],
                                   "ytd": money(total["ytd"]), "prior_ytd": money(total["prior_ytd"])}})

    def line(fn) -> dict[str, Any]:
        return {"months": [money(fn(lambda s: sums[s]["months"][m.isoformat()])) for m in periods],
                "ytd": money(fn(lambda s: sums[s]["ytd"])), "prior_ytd": money(fn(lambda s: sums[s]["prior_ytd"]))}

    gross = line(lambda v: v("Revenue") - v("Cost of sales"))
    # Charges between group entities should cancel. What does not is one side's
    # booking with no counterpart; it is carried here so the group result still
    # equals the sum of the entities' results.
    difference = eliminated["revenue"] - eliminated["costs"] if consolidated else 0
    net = line(lambda v: v("Revenue") - v("Cost of sales") - v("Overheads") + v("Other income"))
    net_ytd_cents = sums["Revenue"]["ytd"] - sums["Cost of sales"]["ytd"] - sums["Overheads"]["ytd"] + sums["Other income"]["ytd"] + difference
    revenue_ytd = sums["Revenue"]["ytd"]
    return {
        "entity": entity, "fin_year": fin_year, "fy_label": f"FY{fin_year - 1}-{str(fin_year)[2:]}",
        "periods": [m.isoformat() for m in periods], "as_at": last.isoformat(),
        "prior_label": f"FY{fin_year - 2}-{str(fin_year - 1)[2:]} same months",
        "has_prior": prior_start >= ends[0].replace(day=1),
        "sections": sections, "gross_profit": gross, "net_before_difference": net,
        "elimination": {"applies": consolidated, "revenue": money(eliminated["revenue"]), "costs": money(eliminated["costs"]),
                        "difference": money(difference)},
        "totals": {"revenue_ytd": money(revenue_ytd), "gross_profit_ytd": gross["ytd"],
                   "gross_margin": round(gross["ytd"] * 100 / revenue_ytd, 4) if revenue_ytd else None,
                   "overheads_ytd": money(sums["Overheads"]["ytd"]), "net_profit_ytd": money(net_ytd_cents),
                   "net_margin": round(net_ytd_cents / revenue_ytd, 4) if revenue_ytd else None,
                   "prior_revenue_ytd": money(sums["Revenue"]["prior_ytd"]),
                   "prior_net_ytd": net["prior_ytd"]},
    }


# ---------------------------------------------------------- balance sheet --
def _balances(entity: str, as_at: date) -> dict[str, Any]:
    """Closing balances in cents, natural sign, with group eliminations applied."""
    where, params = _scope(entity)
    group_ids = _group_ids()
    marks = ", ".join("?" for _ in group_ids)
    rows = db.raw(f"""
        SELECT a.account_code, a.name, a.section, a.type, a.sort_order, a.normal_side,
               (l.counterparty_id IN ({marks})) AS intercompany, sum(l.amount_cents) AS cents
        FROM gl_line l JOIN gl_account a USING (account_code)
        WHERE {where} AND l.posting_date <= ? GROUP BY ALL ORDER BY a.sort_order""", [*group_ids, *params, as_at])
    start = fy_start(fy_of(as_at))
    earned = db.raw(f"""
        SELECT (l.posting_date >= ?) AS current_year, (l.counterparty_id IN ({marks})) AS intercompany, -sum(l.amount_cents) AS cents
        FROM gl_line l JOIN gl_account a USING (account_code)
        WHERE {where} AND a.type IN ('revenue', 'other_income', 'cogs', 'expense') AND l.posting_date <= ?
        GROUP BY ALL""", [start, *group_ids, *params, as_at])
    consolidated = entity == GROUP
    accounts: dict[str, dict[str, Any]] = {}
    eliminated = 0   # signed debit-positive total of intercompany balances removed
    for r in rows:
        if r["type"] not in ("asset", "liability", "equity"):
            continue
        if consolidated and r["intercompany"] and r["account_code"] in (ref.RP_RECEIVABLE, ref.RP_PAYABLE):
            eliminated += r["cents"]
            continue
        acc = accounts.setdefault(r["account_code"], {"account_code": r["account_code"], "name": r["name"],
                                                      "section": r["section"], "type": r["type"], "cents": 0})
        acc["cents"] += r["cents"] * r["normal_side"]
    current_year = sum(e["cents"] for e in earned if e["current_year"])
    prior_years = sum(e["cents"] for e in earned if not e["current_year"])
    return {"accounts": accounts, "current_year": current_year, "prior_years": prior_years, "eliminated": eliminated}


def balance_sheet(entity: str = GROUP, as_at: str | None = None) -> dict[str, Any]:
    ends = month_ends()
    at = date.fromisoformat(as_at) if as_at else ends[-1]
    if at not in ends:
        at = max((m for m in ends if m <= at), default=ends[0])
    year_end = fy_start(fy_of(at)) - timedelta(days=1)
    compare = year_end if year_end in ends else None
    now, then = _balances(entity, at), (_balances(entity, compare) if compare else None)

    def money(c: int) -> float:
        return round(c / 100, 2)

    def build(b: dict[str, Any]) -> dict[str, Any]:
        lines: dict[str, list[dict]] = {s: [] for s in BS_SECTIONS}
        for acc in b["accounts"].values():
            if acc["account_code"] == "3100":
                continue
            lines[acc["section"]].append({"account_code": acc["account_code"], "name": acc["name"], "cents": acc["cents"]})
        if b["eliminated"]:
            lines["Current assets"].append({"account_code": "-", "name": "Unreconciled intercompany balances",
                                            "cents": b["eliminated"], "flag": True})
        retained = b["accounts"].get("3100", {"cents": 0})["cents"] + b["prior_years"]
        lines["Equity"].append({"account_code": "3100", "name": "Retained earnings", "cents": retained})
        lines["Equity"].append({"account_code": "-", "name": "Current year earnings", "cents": b["current_year"]})
        totals = {s: sum(x["cents"] for x in lines[s]) for s in BS_SECTIONS}
        assets = totals["Current assets"] + totals["Non-current assets"]
        liabilities = totals["Current liabilities"] + totals["Non-current liabilities"]
        return {"lines": lines, "totals": totals, "assets": assets, "liabilities": liabilities,
                "net_assets": assets - liabilities, "equity": totals["Equity"]}

    a, p = build(now), (build(then) if then else None)
    sections = []
    for name in BS_SECTIONS:
        prior = {x["name"]: x["cents"] for x in (p["lines"][name] if p else [])}
        names = [x["name"] for x in a["lines"][name]] + [n for n in prior if n not in {x["name"] for x in a["lines"][name]}]
        current = {x["name"]: x for x in a["lines"][name]}
        sections.append({
            "section": name,
            "lines": [{"account_code": current.get(n, {}).get("account_code", "-"), "name": n,
                       "balance": money(current.get(n, {}).get("cents", 0)), "prior": money(prior.get(n, 0)) if p else None,
                       "flag": bool(current.get(n, {}).get("flag"))} for n in names],
            "total": money(a["totals"][name]), "prior_total": money(p["totals"][name]) if p else None})
    working_capital = a["totals"]["Current assets"] - a["totals"]["Current liabilities"]
    return {
        "entity": entity, "as_at": at.isoformat(), "compare_as_at": compare.isoformat() if compare else None,
        "sections": sections,
        "totals": {"assets": money(a["assets"]), "liabilities": money(a["liabilities"]), "net_assets": money(a["net_assets"]),
                   "equity": money(a["equity"]), "difference": money(a["net_assets"] - a["equity"]),
                   "prior_assets": money(p["assets"]) if p else None, "prior_liabilities": money(p["liabilities"]) if p else None,
                   "prior_net_assets": money(p["net_assets"]) if p else None, "prior_equity": money(p["equity"]) if p else None,
                   "working_capital": money(working_capital),
                   "current_ratio": round(a["totals"]["Current assets"] / a["totals"]["Current liabilities"], 2)
                                    if a["totals"]["Current liabilities"] else None,
                   "cash": money(a["lines"]["Current assets"][0]["cents"]) if a["lines"]["Current assets"] else 0,
                   "unreconciled_intercompany": money(now["eliminated"])},
        "balances": a["net_assets"] == a["equity"],
    }


# ---------------------------------------------------------- related party --
def _pair_lines(creditor: str, debtor: str, as_at: date) -> tuple[list[dict], list[dict]]:
    theirs = db.raw("""SELECT posting_date, description, amount_cents AS cents, journal_id FROM gl_line
                        WHERE entity_id = ? AND account_code = ? AND counterparty_id = ? AND posting_date <= ?
                        ORDER BY posting_date, line_id""", [creditor, ref.RP_RECEIVABLE, debtor, as_at])
    ours = db.raw("""SELECT posting_date, description, -amount_cents AS cents, journal_id FROM gl_line
                      WHERE entity_id = ? AND account_code = ? AND counterparty_id = ? AND posting_date <= ?
                      ORDER BY posting_date, line_id""", [debtor, ref.RP_PAYABLE, creditor, as_at])
    return theirs, ours


def _explain(creditor: str, debtor: str, as_at: date) -> list[dict[str, Any]]:
    """Pair off the two ledgers' movements by amount and month; explain what is left."""
    theirs, ours = _pair_lines(creditor, debtor, as_at)
    unmatched_ours = list(ours)
    findings = []
    for t in theirs:
        hit = next((o for o in unmatched_ours if o["cents"] == t["cents"]
                    and abs((o["posting_date"] - t["posting_date"]).days) <= 20), None)
        if hit:
            unmatched_ours.remove(hit)
            continue
        if t["cents"] > 0:
            wrong = _booked_elsewhere(creditor, debtor, t["cents"], t["posting_date"])
            if wrong:
                findings.append({"kind": "wrong_party", "date": t["posting_date"].isoformat(), "amount": t["cents"] / 100,
                                 "booked_to": wrong, "entry": t["description"],
                                 "explanation": f"{creditor} charged {debtor}; {debtor} booked the same amount against {wrong} instead."})
            else:
                findings.append({"kind": "one_sided", "date": t["posting_date"].isoformat(), "amount": t["cents"] / 100,
                                 "entry": t["description"],
                                 "explanation": f"Charged by {creditor} and not found in {debtor}'s ledger."})
        else:
            findings.append({"kind": "unreceipted", "date": t["posting_date"].isoformat(), "amount": t["cents"] / 100,
                             "entry": t["description"], "explanation": f"Receipt in {creditor}'s ledger with no payment in {debtor}'s."})
    for o in unmatched_ours:
        if o["cents"] < 0:
            late = (as_at - o["posting_date"]).days <= 5
            findings.append({"kind": "timing" if late else "unreceipted", "date": o["posting_date"].isoformat(),
                             "amount": o["cents"] / 100, "entry": o["description"],
                             "explanation": (f"Paid by {debtor} on {o['posting_date'].strftime('%d/%m/%Y')}; not yet receipted by {creditor}. "
                                             "Likely timing - expect it to clear next month.") if late else
                                            f"Paid by {debtor} and never receipted by {creditor}."})
        else:
            # A charge only the debtor has: usually the other half of a wrong-party booking.
            findings.append({"kind": "wrong_party_other_half", "date": o["posting_date"].isoformat(), "amount": o["cents"] / 100,
                             "entry": o["description"],
                             "explanation": f"Booked by {debtor} as owing to {creditor}; {creditor} raised no such charge. "
                                            "Check whether it belongs to another related party."})
    return findings


def _booked_elsewhere(creditor: str, debtor: str, cents: int, when: date) -> str | None:
    """The group entity the debtor booked this charge against by mistake, if any:
    one it shows more charges of this amount from than that entity ever raised."""
    for other in _group_ids():
        if other in (creditor, debtor):
            continue
        booked = db.scalar("""SELECT count(*) FROM gl_line WHERE entity_id = ? AND account_code = ? AND counterparty_id = ?
                              AND -amount_cents = ? AND abs(datediff('day', posting_date, ?)) <= 20""",
                           [debtor, ref.RP_PAYABLE, other, cents, when]) or 0
        raised = db.scalar("""SELECT count(*) FROM gl_line WHERE entity_id = ? AND account_code = ? AND counterparty_id = ?
                              AND amount_cents = ? AND abs(datediff('day', posting_date, ?)) <= 20""",
                           [other, ref.RP_RECEIVABLE, debtor, cents, when]) or 0
        if booked > raised:
            return other
    return None


def related_party(as_at: str | None = None) -> dict[str, Any]:
    ends = month_ends()
    at = date.fromisoformat(as_at) if as_at else ends[-1]
    if at not in ends:
        at = max((m for m in ends if m <= at), default=ends[0])
    names = {e["entity_id"]: e["name"] for e in _entities()}
    group = _group_ids()
    bal = db.raw("""SELECT entity_id, counterparty_id,
                            sum(CASE WHEN account_code = ? THEN amount_cents ELSE 0 END) AS receivable,
                            sum(CASE WHEN account_code = ? THEN -amount_cents ELSE 0 END) AS payable
                     FROM gl_line WHERE account_code IN (?, ?) AND posting_date <= ? GROUP BY 1, 2""",
                  [ref.RP_RECEIVABLE, ref.RP_PAYABLE, ref.RP_RECEIVABLE, ref.RP_PAYABLE, at])
    rec = {(b["entity_id"], b["counterparty_id"]): b["receivable"] for b in bal}
    pay = {(b["entity_id"], b["counterparty_id"]): b["payable"] for b in bal}
    pairs = []
    for creditor in group:
        for debtor in group:
            if creditor == debtor:
                continue
            claimed, admitted = rec.get((creditor, debtor), 0), pay.get((debtor, creditor), 0)
            if not claimed and not admitted:
                continue
            difference = claimed - admitted
            pairs.append({"creditor": creditor, "creditor_name": names[creditor], "debtor": debtor, "debtor_name": names[debtor],
                          "receivable": claimed / 100, "payable": admitted / 100, "difference": difference / 100,
                          "agrees": difference == 0,
                          "findings": _explain(creditor, debtor, at) if difference else []})
    outside = [{"entity": e, "entity_name": names[e], "party": c, "party_name": names.get(c, c),
                "receivable": rec.get((e, c), 0) / 100, "payable": pay.get((e, c), 0) / 100}
               for (e, c) in sorted(set(rec) | set(pay)) if c not in group and (rec.get((e, c)) or pay.get((e, c)))]
    trend = db.raw("""WITH m AS (SELECT DISTINCT last_day(posting_date) AS month_end FROM gl_line)
                       SELECT m.month_end, sum(CASE WHEN l.account_code = ? THEN l.amount_cents ELSE 0 END) / 100.0 AS receivable,
                              sum(CASE WHEN l.account_code = ? THEN -l.amount_cents ELSE 0 END) / 100.0 AS payable
                       FROM m JOIN gl_line l ON l.posting_date <= m.month_end
                       WHERE l.account_code IN (?, ?) AND l.counterparty_id IN (SELECT entity_id FROM entity WHERE is_group)
                         AND m.month_end <= ?
                       GROUP BY 1 ORDER BY 1""", [ref.RP_RECEIVABLE, ref.RP_PAYABLE, ref.RP_RECEIVABLE, ref.RP_PAYABLE, at])
    out_of_balance = [p for p in pairs if not p["agrees"]]
    return {
        "as_at": at.isoformat(), "pairs": sorted(pairs, key=lambda p: (-abs(p["difference"]), p["creditor"])),
        "outside_group": outside,
        "matrix": {"entities": group + [o["party"] for o in outside if o["party"] not in group],
                   "names": names,
                   "cells": [{"entity": e, "party": c, "net": (rec.get((e, c), 0) - pay.get((e, c), 0)) / 100}
                             for (e, c) in sorted(set(rec) | set(pay))]},
        "trend": [{"month_end": t["month_end"].isoformat(), "receivable": t["receivable"], "payable": t["payable"],
                   "difference": round(t["receivable"] - t["payable"], 2)} for t in trend],
        "totals": {"receivable": sum(p["receivable"] for p in pairs), "payable": sum(p["payable"] for p in pairs),
                   "difference": round(sum(p["difference"] for p in pairs), 2),
                   "pairs": len(pairs), "out_of_balance": len(out_of_balance),
                   "gross_difference": round(sum(abs(p["difference"]) for p in out_of_balance), 2)},
    }


def pair_ledger(creditor: str, debtor: str, as_at: str | None = None) -> dict[str, Any]:
    at = date.fromisoformat(as_at) if as_at else month_ends()[-1]
    theirs, ours = _pair_lines(creditor, debtor, at)
    since = at - timedelta(days=125)
    fmt = lambda rows: [{"date": r["posting_date"].isoformat(), "description": r["description"], "amount": r["cents"] / 100,  # noqa: E731
                         "journal_id": r["journal_id"]} for r in rows if r["posting_date"] >= since]
    return {"creditor": creditor, "debtor": debtor, "as_at": at.isoformat(), "since": since.isoformat(),
            "creditor_ledger": fmt(theirs), "debtor_ledger": fmt(ours)}
