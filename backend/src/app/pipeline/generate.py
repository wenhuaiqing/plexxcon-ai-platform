"""Generate every synthetic row, deterministically.

Integers decide everything (cents, hundredths of a unit, basis points) and the
only randomness is one seeded generator, so the same code produces the same
bytes on macOS and Linux - which is what lets the image build verify itself
against infra-azure/build.sha256.

Nothing here is real. See pipeline/reference.py for what is assumed and for
the defects seeded on purpose.
"""

from __future__ import annotations

import calendar
import json
import random
from datetime import date, datetime, timedelta
from typing import Any

import duckdb

from src.app.calc import bid as bid_calc
from src.app.calc import trade as trade_calc
from src.app.calc.money import rhu
from src.app.pipeline import reference as ref


def _ins(con: duckdb.DuckDBPyConnection, table: str, rows: list[tuple]) -> None:
    if not rows:
        return
    marks = ", ".join("?" for _ in rows[0])
    con.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)


def _month_starts(first: date, last: date) -> list[date]:
    out, d = [], date(first.year, first.month, 1)
    while d <= last:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def _month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _jitter(rng: random.Random, cents: int, pct: int) -> int:
    """cents moved by up to +/- pct percent, to whole dollars."""
    return (cents * (100 + rng.randint(-pct, pct)) // 100) // 100 * 100


def generate(con: duckdb.DuckDBPyConnection) -> None:
    rng = random.Random(ref.SEED)
    _core(con)
    _ledger(con, rng)
    _bids(con, rng)
    _trade_planner(con, rng)
    _material_register(con, rng)


# ------------------------------------------------------------------- core --
def _core(con: duckdb.DuckDBPyConnection) -> None:
    _ins(con, "entity", [(i, n, d, True) for i, n, d in ref.ENTITIES]
         + [(i, n, "Related party outside the group", False) for i, n in ref.RELATED_NON_GROUP])
    _ins(con, "project", [(j, n, c, s, r, v * 100, a, b, st) for j, n, c, s, r, v, a, b, st in ref.PROJECTS])
    _ins(con, "gl_account", [(c, n, t, s, side, i) for i, (c, n, t, s, side) in enumerate(ref.ACCOUNTS)])


# ----------------------------------------------------------------- ledger --
class _Ledger:
    def __init__(self) -> None:
        self.rows: list[tuple] = []
        self.journal = 0

    def post(self, entity: str, when: date, description: str, source: str, lines: list[tuple], project: str | None = None) -> None:
        """lines: (account, signed cents, counterparty or None). Must sum to zero."""
        lines = [ln for ln in lines if ln[1] != 0]
        if not lines:
            return
        if sum(ln[1] for ln in lines) != 0:
            raise ValueError(f"unbalanced journal: {description}")
        self.journal += 1
        jid = f"JNL-{self.journal:05d}"
        for account, cents, counterparty in lines:
            self.rows.append((len(self.rows) + 1, jid, entity, when, account, cents, counterparty, project, description, source))


def _ledger(con: duckdb.DuckDBPyConnection, rng: random.Random) -> None:
    gl = _Ledger()
    opening = date(2025, 7, 1)
    D = 100  # dollars to cents

    def open_entity(entity: str, balances: list[tuple[str, int]]) -> None:
        lines = [(a, c * D, None) for a, c in balances]
        lines.append(("3100", -sum(c for _, c, _ in lines), None))
        gl.post(entity, opening, "Opening balances at 30/06/2025", "opening", lines)

    open_entity("CON", [("1000", 1_850_000), ("1100", 1_400_000), ("1150", 310_000), ("2000", -1_150_000),
                        ("2200", -140_000), ("3000", -100)])
    open_entity("PLT", [("1000", 220_000), ("1500", 2_400_000), ("1510", -900_000), ("2300", -700_000), ("3000", -100)])
    open_entity("PROP", [("1000", 90_000), ("1600", 4_200_000), ("2300", -2_600_000), ("3000", -1_000_000)])
    open_entity("HOLD", [("1000", 940_000), ("3000", -1_000)])

    hire, rent, fee = 46_200 * D, 38_500 * D, 22_000 * D
    seeds = ref.SEEDED
    assert seeds["rp_one_sided"]["amount_cents"] == hire and seeds["rp_timing"]["amount_cents"] == rent
    assert seeds["rp_wrong_party"]["amount_cents"] == fee

    debtors_prev, creditors_prev, payroll_prev = 1_400_000 * D, 1_150_000 * D, 140_000 * D
    retention_held: dict[str, int] = {}
    owed = {"PLT": 0, "PROP": 0, "HOLD": 0}   # what the builder booked last month and pays this month

    for start in _month_starts(ref.LEDGER_START, ref.LEDGER_END):
        end = _month_end(start)
        key = start.strftime("%Y-%m")
        mid = start + timedelta(days=14)
        label = start.strftime("%m/%Y")

        # ---- the builder: claims, costs, overheads
        billed = 0
        subs = materials = labour = plant = 0
        for job, name, _c, _s, _r, value, p_start, p_end, _st in ref.PROJECTS:
            if p_end < start or p_start > end:
                continue
            months = max(len(_month_starts(p_start, p_end)), 1)
            claim = _jitter(rng, value * D // months, 12)
            retention = claim * 5 // 100
            gl.post("CON", end, f"Progress claim {label} - {name}", "claims",
                    [("1100", claim - retention, None), ("1150", retention, None), ("4000", -claim, None)], job)
            billed += claim - retention
            retention_held[job] = retention_held.get(job, 0) + retention
            if rng.randint(1, 5) == 1:
                variation = _jitter(rng, claim * 6 // 100, 40)
                gl.post("CON", end, f"Approved variation {label} - {name}", "claims",
                        [("1100", variation, None), ("4100", -variation, None)], job)
                billed += variation
            s, m, lab, p = (_jitter(rng, claim * pct // 100, 10) for pct in (47, 16, 13, 3))
            gl.post("CON", end, f"Subcontractor claims {label} - {name}", "payables", [("5000", s, None), ("2000", -s, None)], job)
            gl.post("CON", end, f"Materials {label} - {name}", "payables", [("5100", m, None), ("2000", -m, None)], job)
            gl.post("CON", end, f"External plant hire {label} - {name}", "payables", [("5300", p, None), ("2000", -p, None)], job)
            withheld = lab * 12 // 100
            gl.post("CON", end, f"Site wages {label} - {name}", "payroll",
                    [("5200", lab, None), ("1000", -(lab - withheld), None), ("2200", -withheld, None)], job)
            subs, materials, labour, plant = subs + s, materials + m, labour + withheld, plant + p
            if (p_end.year, p_end.month) == (start.year, start.month):
                held = retention_held.pop(job, 0) // 2
                gl.post("CON", end, f"Retention released at practical completion - {name}", "receipts",
                        [("1000", held, None), ("1150", -held, None)], job)
        gl.post("CON", mid, f"Receipts from debtors {label}", "receipts", [("1000", debtors_prev, None), ("1100", -debtors_prev, None)])
        gl.post("CON", mid, f"Creditor payment run {label}", "payments", [("2000", creditors_prev, None), ("1000", -creditors_prev, None)])
        gl.post("CON", mid, f"PAYG and superannuation {label}", "payroll", [("2200", payroll_prev, None), ("1000", -payroll_prev, None)])
        debtors_prev, creditors_prev, payroll_prev = billed, subs + materials + plant, labour
        for account, base in (("6000", 140_000), ("6200", 12_000), ("6300", 8_500), ("6400", 6_800), ("6900", 9_500)):
            amount = _jitter(rng, base * D, 6)
            gl.post("CON", end, f"Overheads {label}", "overheads", [(account, amount, None), ("1000", -amount, None)])

        # ---- settle last month's related-party charges (both sides)
        for party, amount in owed.items():
            if amount:
                gl.post("CON", mid, f"Paid {party} for prior month", "intercompany", [("2800", amount, party), ("1000", -amount, None)])
                gl.post(party, mid, "Received from CON for prior month", "intercompany", [("1000", amount, None), ("1800", -amount, "CON")])
        owed = {"PLT": hire, "PROP": rent, "HOLD": fee}

        # ---- this month's related-party charges, with the seeded breaks
        gl.post("PLT", end, f"Plant hire to CON {label}", "intercompany", [("1800", hire, "CON"), ("4800", -hire, "CON")])
        if key == seeds["rp_one_sided"]["month"]:
            owed["PLT"] = 0  # never booked by the builder, so never paid either
        else:
            gl.post("CON", end, f"Plant hire from PLT {label}", "intercompany", [("5310", hire, "PLT"), ("2800", -hire, "PLT")])
        gl.post("PROP", end, f"Rent to CON {label}", "intercompany", [("1800", rent, "CON"), ("4800", -rent, "CON")])
        gl.post("CON", end, f"Rent from PROP {label}", "intercompany", [("6100", rent, "PROP"), ("2800", -rent, "PROP")])
        gl.post("HOLD", end, f"Management fee to CON {label}", "intercompany", [("1800", fee, "CON"), ("4800", -fee, "CON")])
        if key == seeds["rp_wrong_party"]["month"]:
            gl.post("CON", end, f"Management fee {label}", "intercompany", [("6110", fee, "PROP"), ("2800", -fee, "PROP")])
            owed["HOLD"] = 0  # sits on the wrong ledger card, so the payment run misses it
        else:
            gl.post("CON", end, f"Management fee from HOLD {label}", "intercompany", [("6110", fee, "HOLD"), ("2800", -fee, "HOLD")])
        if end == ref.LEDGER_END:
            gl.post("CON", end, "Rent paid to PROP in advance of month end", "intercompany",
                    [("2800", rent, "PROP"), ("1000", -rent, None)])
            owed["PROP"] = 0

        # ---- the other entities' own costs
        gl.post("PLT", end, f"Depreciation {label}", "fixed assets", [("6500", 28_000 * D, None), ("1510", -28_000 * D, None)])
        gl.post("PLT", end, f"Loan interest {label}", "bank", [("6600", 3_900 * D, None), ("1000", -3_900 * D, None)])
        wages = _jitter(rng, 21_000 * D, 5)
        gl.post("PLT", end, f"Workshop wages {label}", "payroll", [("6000", wages, None), ("1000", -wages, None)])
        gl.post("PROP", end, f"Depreciation {label}", "fixed assets", [("6500", 8_750 * D, None), ("1510", -8_750 * D, None)])
        gl.post("PROP", end, f"Loan interest {label}", "bank", [("6600", 13_200 * D, None), ("1000", -13_200 * D, None)])
        admin = _jitter(rng, 15_500 * D, 5)
        gl.post("HOLD", end, f"Group administration {label}", "overheads", [("6000", admin, None), ("1000", -admin, None)])
        gl.post("HOLD", end, f"Sundry {label}", "overheads", [("6900", 2_100 * D, None), ("1000", -2_100 * D, None)])

        # ---- loans
        if key == "2025-09":
            gl.post("HOLD", mid, "Loan advanced to PLT for plant purchase", "loans", [("1800", 600_000 * D, "PLT"), ("1000", -600_000 * D, None)])
            gl.post("PLT", mid, "Loan received from HOLD", "loans", [("1000", 600_000 * D, None), ("2800", -600_000 * D, "HOLD")])
            gl.post("PLT", end, "Plant purchased", "fixed assets", [("1500", 640_000 * D, None), ("1000", -640_000 * D, None)])
        if key > "2025-09":
            gl.post("PLT", end, f"Loan repayment to HOLD {label}", "loans", [("2800", 15_000 * D, "HOLD"), ("1000", -15_000 * D, None)])
            gl.post("HOLD", end, f"Loan repayment from PLT {label}", "loans", [("1000", 15_000 * D, None), ("1800", -15_000 * D, "PLT")])
        if key == "2025-12":
            gl.post("CON", mid, "Advance to directors", "loans", [("1800", 120_000 * D, "DIR"), ("1000", -120_000 * D, None)])
        if key >= "2026-03":
            gl.post("CON", end, f"Directors' loan repayment {label}", "loans", [("1000", 5_000 * D, None), ("1800", -5_000 * D, "DIR")])

    _ins(con, "gl_line", gl.rows)


# -------------------------------------------------------------------- bids --
DIRECT_BY_SECTOR = {
    "Remedial": ["0200", "0430", "0700", "1100", "0600"],
    "Body corporate": ["0200", "0700", "0800", "1100", "1200"],
    "Industrial": ["0300", "0400", "0410", "0420", "0500", "1700"],
    "Commercial": ["0300", "0400", "0410", "0500", "0900", "1000", "1300", "1400", "1500"],
}
INDIRECT = ["0100", "0110", "0120", "0140"]
PROSPECTS = [
    # bid number, name, company, sector, GBA m2, cost ($), stage
    ("B-2601", "Harbour Road warehouse extension", "Harbour Road Logistics Pty Ltd", "Industrial", 6400, 6_950_000, "won"),
    ("B-2604", "Kirra Point carpark concrete repair", "Body Corporate for Kirra Point", "Remedial", 5200, 1_720_000, "won"),
    ("B-2607", "Eagle Farm food plant upgrade", "Eastside Foods Pty Ltd", "Industrial", 4100, 5_640_000, "won"),
    ("B-2609", "Tugun apartments facade repaint", "Body Corporate for Tugun Sands", "Body corporate", 3800, 980_000, "lost"),
    ("B-2612", "Maroochy medical centre fitout and extension", "Coastline Health Property Trust", "Commercial", 2900, 4_610_000, "won"),
    ("B-2615", "Palm Court roof and membrane renewal", "Body Corporate for Palm Court", "Body corporate", 2100, 1_270_000, "won"),
    ("B-2618", "Pinkenba chemical store bund repair", "Portside Chemicals Pty Ltd", "Industrial", 1500, 1_340_000, "lost"),
    ("B-2620", "Wynnum depot amenities building", "Bayside Transport Group Pty Ltd", "Commercial", 950, 1_930_000, "won"),
    ("B-2623", "Southport office tower column strengthening", "Southport Central Investments Pty Ltd", "Remedial", 7200, 3_280_000, "won"),
    ("B-2626", "Caloundra resort pool deck remediation", "Body Corporate for Caloundra Shores", "Remedial", 1800, 1_150_000, "lost"),
    ("B-2629", "Yatala distribution centre hardstand", "Southern Freight Hub Pty Ltd", "Industrial", 12500, 4_420_000, "submitted"),
    ("B-2631", "Chermside medical suites refurbishment", "Northside Clinics Pty Ltd", "Commercial", 1600, 2_380_000, "submitted"),
    ("B-2634", "Burleigh apartments balcony waterproofing", "Body Corporate for Burleigh Crest", "Body corporate", 4300, 1_690_000, "tendering"),
    ("B-2636", "Lytton cold store dock levellers and slab", "Bayport Cold Chain Pty Ltd", "Industrial", 3200, 2_760_000, "tendering"),
    ("B-2638", "Noosa civic centre roof replacement", "Hinterland Shire Facilities", "Commercial", 2700, 1_880_000, "tendering"),
    ("B-2640", "Mooloolaba unit block concrete cancer repair", "Body Corporate for Mooloolaba Views", "Remedial", 3600, 2_140_000, "qualifying"),
]


def _bid_data(rng: random.Random, prospect: tuple, estimator: str, submitted: date) -> dict[str, Any]:
    number, name, company, sector, gba, cost, _stage = prospect
    codes = DIRECT_BY_SECTOR[sector]
    labels = {c: d for c, d, _ in ref.COST_CODES}
    weights = [rng.randint(6, 30) for _ in codes]
    direct_total = cost * 86 // 100
    direct = [{"cost_code": c, "description": labels[c], "amount": str(direct_total * w // sum(weights) // 100 * 100)}
              for c, w in zip(codes, weights)]
    ind_weights = [rng.randint(8, 30) for _ in INDIRECT]
    indirect = [{"cost_code": c, "description": labels[c], "amount": str((cost - direct_total) * w // sum(ind_weights) // 100 * 100)}
                for c, w in zip(INDIRECT, ind_weights)]
    establishment = submitted + timedelta(days=rng.randint(40, 75))
    completion = establishment + timedelta(weeks=rng.randint(26, 52))
    rivals = rng.sample(ref.COMPETITORS, rng.randint(2, 3))
    return {
        "project": {"bid_name": name, "bid_number": number, "sector": sector, "client": company,
                    "location": rng.choice(["Brisbane", "Gold Coast", "Sunshine Coast"]),
                    "gross_building_area": str(gba), "bid_gate": rng.choice(["Gate 2 - Tender", "Gate 3 - Final price"]),
                    "estimator": estimator},
        "programme": {"submission_date": submitted.isoformat(),
                      "contract_execution": (submitted + timedelta(days=rng.randint(21, 35))).isoformat(),
                      "site_establishment": establishment.isoformat(), "practical_completion": completion.isoformat(),
                      "included_delays": str(rng.choice([5, 8, 10, 12, 15]))},
        "direct": direct, "indirect": indirect,
        "margin": {"contingency_pct": str(rng.choice(["2.0", "2.5", "3.0", "4.0"])),
                   "margin_pct": str(rng.choice(["6.5", "7.0", "8.0", "9.0", "10.0", "11.5"])), "escalation": str(rng.choice([0, 15000, 25000, 40000]))},
        "competitors": [{"name": r, "note": rng.choice(["Incumbent on the site", "Priced the last stage", "Known to be busy",
                                                         "Usually sharp on preliminaries"])} for r in rivals],
        "benchmarking": {"comparable": rng.choice(["Similar scope delivered last year", "No direct comparable; rate built up from first principles",
                                                   "Two comparable jobs in the same sector"]), "notes": ""},
    }


def revision_row(bid_id: str, revision: int, latest: bool, at: datetime, by: str, data: dict[str, Any],
                 acknowledged: str = "") -> tuple:
    t = bid_calc.totals(data)
    p, g = data["project"], data["programme"]
    d = lambda v: date.fromisoformat(v) if v else None  # noqa: E731
    return (bid_id, revision, latest, at, by, p["bid_name"], p["bid_number"], p.get("sector"), p.get("client"),
            t["gross_building_area_m2"], d(g.get("site_establishment")), d(g.get("practical_completion")),
            d(g.get("submission_date")), t["direct_cents"], t["indirect_cents"], t["contingency_cents"],
            t["escalation_cents"], t["grand_total_cents"], t["margin_bp"], t["margin_cents"], t["final_ex_cents"],
            t["final_inc_cents"], t["rate_per_m2_cents"], acknowledged, json.dumps(data, sort_keys=True))


def cost_line_rows(bid_id: str, revision: int, data: dict[str, Any]) -> list[tuple]:
    from src.app.calc.money import to_cents
    rows = []
    for grid in ("direct", "indirect"):
        for i, line in enumerate(data.get(grid) or [], start=1):
            if str(line.get("amount") or "").strip() == "" and not line.get("description"):
                continue
            rows.append((bid_id, revision, grid, i, line.get("cost_code") or "", line.get("description") or "",
                         to_cents(line.get("amount"))))
    return rows


def _bids(con: duckdb.DuckDBPyConnection, rng: random.Random) -> None:
    deals, bids, revisions, lines, rivals, drafts = [], [], [], [], [], []
    estimators = ref.PEOPLE["estimators"]
    for i, prospect in enumerate(PROSPECTS):
        number, name, company, sector, _gba, cost, stage = prospect
        deal_id = str(48_210_000 + i * 137)
        submitted = date(2025, 11, 10) + timedelta(days=i * 23)
        if stage in ("tendering", "qualifying"):
            submitted = ref.DEMO_TODAY + timedelta(days=10 + i)
        owner = estimators[i % len(estimators)]
        final_ex = 0
        if stage != "qualifying" and number != "B-2638":   # B-2638 has no summary yet: the "new blank" case
            bid_id = f"BID-{i + 1:03d}"
            data = _bid_data(rng, prospect, owner, submitted)
            n_revisions = 1 if stage == "tendering" else rng.randint(1, 3)
            first = datetime.combine(min(submitted, ref.DEMO_TODAY) - timedelta(days=9 * n_revisions), datetime.min.time()) + timedelta(hours=15)
            for rev in range(1, n_revisions + 1):
                if rev > 1:   # a price change: margin moves and one line is repriced
                    data = json.loads(json.dumps(data))
                    data["margin"]["margin_pct"] = str(max(4.0, float(data["margin"]["margin_pct"]) - rng.choice([0.5, 1.0, 1.5])))
                    line = data["direct"][rng.randrange(len(data["direct"]))]
                    line["amount"] = str(int(line["amount"]) * rng.choice([94, 96, 103, 105]) // 100 // 100 * 100)
                at = first + timedelta(days=8 * (rev - 1), minutes=rng.randint(0, 90))
                revisions.append(revision_row(bid_id, rev, rev == n_revisions, at, owner, data))
                lines += cost_line_rows(bid_id, rev, data)
                rivals += [(bid_id, rev, c["name"], c["note"]) for c in data["competitors"]]
                final_ex = bid_calc.totals(data)["final_ex_cents"]
            bids.append((bid_id, number, deal_id, name, sector, n_revisions, first, owner))
            if number == "B-2634":   # a shared draft someone has open: the register's "In progress" chip
                draft = json.loads(json.dumps(data))
                draft["margin"]["margin_pct"] = "8.5"
                drafts.append(("DRF-0001", bid_id, deal_id, "Estimator B", n_revisions, 3, json.dumps(draft, sort_keys=True),
                               ref.DEMO_NOW - timedelta(hours=18), ref.DEMO_NOW - timedelta(minutes=40), "Estimator B"))
        amount = final_ex or cost * 108
        close = submitted + timedelta(days=30)
        deals.append((deal_id, number, name, company, sector, amount, stage, close, owner,
                      datetime.combine(min(submitted, ref.DEMO_TODAY), datetime.min.time()) + timedelta(hours=16)))
    _ins(con, "crm_deal", deals)
    _ins(con, "bid", bids)
    _ins(con, "bid_revision", revisions)
    _ins(con, "bid_cost_line", lines)
    _ins(con, "bid_competitor", rivals)
    _ins(con, "bid_draft", drafts)
    _ins(con, "bid_presence", [("DRF-0001", "Estimator B", ref.DEMO_NOW - timedelta(minutes=40))])
    audit = [(r[3], r[4], "bid_summary", None, f"{r[6]} revision {r[1]}", "submit revision", "recorded",
              f"{r[5]}: final excl. tax ${r[20] / 100:,.0f}", None) for r in sorted(revisions, key=lambda r: r[3])]
    _audit(con, audit)


def _audit(con: duckdb.DuckDBPyConnection, rows: list[tuple]) -> None:
    """rows: (ts, actor, system, project_id, subject, action, outcome, detail, reason)."""
    start = con.execute("SELECT coalesce(max(audit_id), 0) FROM audit_log").fetchone()[0]
    _ins(con, "audit_log", [(start + i, *r) for i, r in enumerate(rows, start=1)])


# ----------------------------------------------------------- trade planner --
def rate_library() -> list[tuple]:
    rows = []
    at = datetime(2026, 7, 1, 9, 0)
    for trade, code, tasks in ref.TRADES:
        for i, (task, unit, rate, crew) in enumerate(tasks, start=1):
            rows.append((f"{code}-{i * 10:03d}", trade, code, task, unit, rate, crew, at, "Estimating lead"))
    return rows


def request_rows(request_id: str, root: str, version: int, title: str, status: str, author: str,
                 created: datetime, scope: dict[str, Any], rates: dict[str, dict[str, Any]],
                 reviewer: str | None = None, feedback: str | None = None) -> tuple[tuple, list[tuple], list[tuple]]:
    r = trade_calc.calculate(scope, rates)
    d = lambda v: date.fromisoformat(v) if v else None  # noqa: E731
    submitted = None if status == "draft" else created + timedelta(hours=3)
    reviewed = submitted + timedelta(days=1, hours=2) if reviewer else None
    head = (request_id, root, version, scope["project"]["project_id"], title, status, author, created,
            reviewed or submitted or created, submitted, reviewer, reviewed, feedback, json.dumps(scope, sort_keys=True),
            r["total_hours_x100"], r["labour_cents"], r["non_production_cents"], r["materials_cents"], r["plant_cents"],
            r["total_cents"], r["peak_crew"], d(r["target_finish"]), d(r["finish_date"]), r["on_time"])
    trades = [(request_id, t["trade"], t["trade_code"], t["mobilisation"], t["classification"], t["crew_size"],
               t["hours_x100"], t["ordinary_hours_x100"], t["overtime_hours_x100"], t["work_days"], d(t["start_date"]),
               d(t["finish_date"]), d(t["target_finish"]), t["on_time"], t["labour_cents"]) for t in r["trades"]]
    tasks = [(request_id, t["trade"], t["seq"], t["cost_code"], t["location"], t["task"], t["rate_code"], t["unit"],
              t["quantity_x100"], t["rate_x1000"], t["modifier_x10000"], t["hours_x100"]) for t in r["tasks"]]
    return head, trades, tasks


def _scope(rng: random.Random, job: str, start: date, weeks: int, trades: list[tuple[str, int, int]],
           levels: int, hours: str = "8", scale: int = 100, waive: bool = False, advanced: bool = False) -> dict[str, Any]:
    locations = [{"zone": "A", "basements": 1 if levels > 3 else 0, "grounds": 1, "levels": levels, "units_per_level": 4}]
    codes = [c["code"] for c in trade_calc.location_codes(job, locations)]
    mobs = [{"id": "M1", "name": "Mobilisation 1", "start": start.isoformat()},
            {"id": "M2", "name": "Mobilisation 2", "start": (start + timedelta(weeks=max(weeks // 3, 1))).isoformat()}]
    library = {t: (c, tasks) for t, c, tasks in ref.TRADES}
    out = []
    for name, crew, mob in trades:
        code, tasks = library[name]
        rows = []
        for i, (_task, _unit, rate, _crew) in enumerate(tasks[: rng.randint(2, len(tasks))], start=1):
            # sized in worker-hours, so a crew of the default size is busy for weeks, not days
            qty = rate * rng.randint(260, 760) * scale // 100 // 1000
            mods = {"access": rng.choice([100, 100, 85]), "complexity": rng.choice([100, 90]),
                    "crew_mix": 100, "handling": rng.choice([100, 88])} if advanced else {}
            rows.append({"rate_code": f"{code}-{i * 10:03d}", "location": codes[(i + crew) % len(codes)],
                         "quantity": str(max(qty, 1)), "modifiers": mods})
        out.append({"trade": name, "mobilisation_id": f"M{mob}", "crew_size": crew,
                    "classification": "Labourer" if name == "Labouring" else "Tradesperson", "tasks": rows})
    return {
        "project": {"project_id": job, "target_start": start.isoformat(),
                    "target_finish": (start + timedelta(weeks=weeks)).isoformat(), "hours_per_day": hours,
                    "work_saturdays": False, "mobilisations": mobs},
        "locations": locations, "trades": out,
        "non_production": {"waived": True, "roles": []} if waive else
                          {"waived": False, "roles": [{"role": "Supervisor", "count": 1, "weeks": weeks},
                                                      {"role": "Leading hand", "count": 1, "weeks": max(weeks - 2, 1)}]},
        "financials": {"materials": [{"description": "Consumables and fixings", "amount": str(rng.randint(8, 30) * 1000)}],
                       "plant": [{"description": "Access equipment", "weeks": str(weeks // 2), "rate_per_week": str(rng.randint(9, 22) * 100)}]},
        "advanced": advanced,
    }


def _trade_planner(con: duckdb.DuckDBPyConnection, rng: random.Random) -> None:
    library = rate_library()
    _ins(con, "tp_rate", library)
    rates = {r[0]: {"rate_code": r[0], "trade": r[1], "task": r[3], "unit": r[4], "rate_x1000": r[5]} for r in library}
    sup = ref.PEOPLE["supervisors"]
    plan = [
        # id, root, version, title, status, author, created, job, start, weeks, trades, levels, extra, reviewer, feedback
        ("TR-0001", "TR-0001", 1, "Structure - base request", "accepted", sup[0], datetime(2026, 2, 9, 10, 0), "2418", date(2026, 3, 2), 22,
         [("Formwork", 6, 1), ("Steel fixing", 5, 1), ("Concrete placing", 6, 2), ("Labouring", 3, 1)], 2, {},
         "Construction manager", "Crew sizes agree with the programme. Accepted as the base."),
        ("TR-0002", "TR-0002", 1, "Top-up: mezzanine added by variation", "accepted", sup[0], datetime(2026, 8, 18, 9, 30), "2418", date(2026, 9, 7), 8,
         [("Formwork", 4, 1), ("Steel fixing", 3, 1), ("Concrete placing", 4, 2)], 1, {"scale": 45},
         "Construction manager", "Matches the approved variation. Accepted as a top-up to TR-0001."),
        ("TR-0003", "TR-0003", 1, "Slab replacement and finishes", "pending", sup[1], datetime(2026, 11, 11, 14, 0), "2427", date(2026, 11, 30), 14,
         [("Concrete repair", 4, 1), ("Concrete placing", 5, 2), ("Painting and coatings", 3, 2), ("Labouring", 2, 1)], 1, {"advanced": True, "scale": 42}, None, None),
        ("TR-0004", "TR-0004", 1, "Fitout labour", "rejected", sup[2], datetime(2026, 10, 6, 11, 0), "2431", date(2026, 10, 26), 10,
         [("Carpentry", 3, 1), ("Painting and coatings", 2, 2)], 2, {"waive": True, "scale": 60},
         "Commercial manager", "The finish date runs well past the target with a crew of three. Revise the crew or the scope."),
        ("TR-0005", "TR-0004", 2, "Fitout labour", "pending", sup[2], datetime(2026, 11, 12, 8, 45), "2431", date(2026, 11, 23), 12,
         [("Carpentry", 6, 1), ("Painting and coatings", 4, 2), ("Labouring", 2, 1)], 2, {"scale": 60}, None, None),
        ("TR-0006", "TR-0006", 1, "Roof membrane renewal", "tentative", sup[1], datetime(2026, 11, 4, 15, 20), "2436", date(2026, 11, 23), 9,
         [("Waterproofing", 4, 1), ("Labouring", 2, 1)], 1, {"hours": "10", "scale": 85},
         "Construction manager", "Ten-hour days need the body corporate's agreement on site hours first. Holding until that is confirmed."),
        ("TR-0007", "TR-0007", 1, "Amenities building structure", "draft", sup[0], datetime(2026, 11, 13, 16, 10), "2440", date(2026, 12, 7), 12,
         [("Formwork", 4, 1), ("Steel fixing", 3, 1)], 1, {}, None, None),
        ("TR-0008", "TR-0008", 1, "Balcony rectification - stage 2", "accepted", sup[2], datetime(2026, 6, 22, 13, 0), "2412", date(2026, 7, 13), 18,
         [("Concrete repair", 5, 1), ("Waterproofing", 4, 2), ("Painting and coatings", 3, 2)], 4, {"advanced": True, "scale": 50},
         "Commercial manager", "Rates sit inside the library. Accepted."),
    ]
    heads, trades, tasks, audit = [], [], [], []
    for rid, root, version, title, status, author, created, job, start, weeks, tr, levels, extra, reviewer, feedback in plan:
        scope = _scope(rng, job, start, weeks, tr, levels, **extra)
        head, t, k = request_rows(rid, root, version, title, status, author, created, scope, rates, reviewer, feedback)
        heads.append(head)
        trades += t
        tasks += k
        if status != "draft":
            audit.append((head[9], author, "trade_planner", job, rid, "submit for approval", "recorded", title, None))
        if reviewer:
            audit.append((head[11], reviewer, "trade_planner", job, rid, f"review: {status}", "recorded", title, feedback))
    _ins(con, "tp_request", heads)
    _ins(con, "tp_request_trade", trades)
    _ins(con, "tp_request_task", tasks)
    _audit(con, sorted(audit, key=lambda r: r[0]))


# ------------------------------------------------- material supply register --
CONCRETE_ELEMENTS = [("Footings", "Pad and strip footings", "N32/20", 62), ("Slab on ground", "Warehouse slab", "N40/20", 148),
                     ("Columns", "Ground to roof", "S40/20", 34), ("Suspended slab", "Level 1", "N40/20", 96),
                     ("Walls", "Core and retaining walls", "N32/20", 58), ("Stairs and landings", "Stair cores", "N32/20", 18)]
REO_ELEMENTS = [("Footings", "Pad and strip footings", "Cut and bent bar", 7), ("Slab on ground", "Warehouse slab", "Mesh", 14),
                ("Columns", "Ground to roof", "Cut and bent bar", 6), ("Suspended slab", "Level 1", "Cut and bent bar", 12)]


def price_at(prices: list[tuple], project: str, supplier: str, item: str, when: date) -> int:
    for p in prices:
        if (p[1], p[3], p[4], p[5]) == (project, supplier, "base", item) and p[9] <= when and (p[10] is None or when <= p[10]):
            return p[7]
    raise KeyError((project, supplier, item, when))


def _material_register(con: duckdb.DuckDBPyConnection, rng: random.Random) -> None:
    admin = ref.PEOPLE["admins"]
    today = ref.DEMO_TODAY
    enrol, budget, prices, deliveries, dockets, invoices, inv_lines, audit = [], [], [], [], [], [], [], []
    docs: list[dict[str, Any]] = []
    starts = {p[0]: p[6] for p in ref.PROJECTS}
    rise = ref.PRICE_RISE_FROM
    docket_seq = {"CPM": 48_100, "RLC": 771_000, "SFR": 400}
    pending_pours: dict[str, list[tuple]] = {}

    for pi, job in enumerate(ref.MSR_PROJECTS):
        who = admin[pi % 2]
        t0 = datetime.combine(starts[job], datetime.min.time()) + timedelta(hours=9)
        enrol.append((job, t0, who))
        audit.append((t0, who, "material_register", job, f"Job {job}", "enrol project", "recorded", "Concrete and reinforcement registers opened", None))
        sup_code, sup_name = ref.CONCRETE_SUPPLIERS[pi % 2]
        scale = [100, 82, 64, 46][pi]

        # ---- price lists: a base rate per item, with the July rise as a second dated row
        def add_price(register: str, supplier: str, kind: str, item: str, unit: str, rate: int, waived: bool,
                      start: date, end: date | None) -> None:
            prices.append((f"PR-{len(prices) + 1:04d}", job, register, supplier, kind, item, unit, rate, waived, start, end,
                           None, t0, who, None, None))

        for item, rate in ref.CONCRETE_ITEMS:
            rate += pi * 300
            add_price("concrete", sup_name, "base", item, "m3", rate, False, date(2026, 1, 1), rise - timedelta(days=1))
            add_price("concrete", sup_name, "base", item, "m3", rhu(rate * (10000 + ref.PRICE_RISE_BP), 10000), False, rise, None)
        for item, rate in ref.REO_ITEMS:
            add_price("reo", ref.REO_SUPPLIER[1], "base", item, "t", rate + pi * 1500, False, date(2026, 1, 1), None)
        add_price("concrete", sup_name, "surcharge", "Saturday delivery", "per m3", 1800, False, date(2026, 1, 1), None)
        # one job negotiated the small-load fee away: listed at $0 and tagged waived, not left off
        add_price("concrete", sup_name, "surcharge", "Small load under 3 m3", "per load", 0 if job == "2427" else 9500,
                  job == "2427", date(2026, 1, 1), None)
        if job != ref.SEEDED["msr_waiting_time"]["project"]:
            add_price("concrete", sup_name, "surcharge", "Waiting time", "per 15 min", 4500, False, date(2026, 1, 1), None)

        # ---- budget lines, pours and dockets
        for register, elements, supplier, unit in (("concrete", CONCRETE_ELEMENTS, sup_name, "m3"),
                                                   ("reo", REO_ELEMENTS, ref.REO_SUPPLIER[1], "t")):
            code = sup_code if register == "concrete" else "SFR"
            for ei, (element, sub, item, base_qty) in enumerate(elements):
                qty = base_qty * scale * 100 // 100            # x100
                rate = price_at(prices, job, supplier, item, date(2026, 1, 1))
                fac = qty * rng.choice([102, 103, 104, 106]) // 100
                line_id = f"BL-{len(budget) + 1:04d}"
                n = max(2, min(5, base_qty // 30 + 2)) if register == "concrete" else 2
                first = starts[job] + timedelta(weeks=3 + ei * 5)
                delivered_line = 0
                for k in range(n):
                    when = first + timedelta(weeks=2 * k, days=rng.choice([0, 1, 2, 3]))
                    while when.weekday() >= 5:
                        when += timedelta(days=1)
                    planned = qty // n
                    did = f"DL-{len(deliveries) + 1:04d}"
                    label = f"{element} - pour {k + 1} of {n}" if register == "concrete" else f"{element} - bar schedule {k + 1} of {n}"
                    deliveries.append((did, job, register, line_id, label, supplier, item, when, planned, t0, who, None, None))
                    if when >= today:
                        continue
                    if when >= today - timedelta(days=16):     # delivered in the last fortnight: paperwork is still in the inbox
                        pending_pours.setdefault(job, []).append((did, register, supplier, code, item, when, planned, label))
                        continue
                    actual = planned * rng.randint(96, 102) // 100
                    loads = [actual] if register == "reo" else []
                    remaining = actual
                    while register == "concrete" and remaining > 0:
                        load = min(remaining, rng.choice([560, 600, 640, 700, 740]))
                        loads.append(load)
                        remaining -= load
                    for load in loads:
                        docket_seq[code] += rng.randint(1, 9)
                        no = f"{code}-{docket_seq[code]}" if code != "SFR" else f"BS-{docket_seq[code]:04d}"
                        dockets.append((f"DK-{len(dockets) + 1:05d}", did, job, register, no, when, item, load, None,
                                        datetime.combine(when, datetime.min.time()) + timedelta(hours=16), who, None, None))
                        delivered_line += load
                if job == ref.SEEDED["msr_fac_overrun"]["project"] and register == "concrete" and element == "Footings":
                    fac = delivered_line * 93 // 100            # seeded: delivered already past the forecast
                budget.append((line_id, job, register, element, sub, unit, qty, rate, fac, rate, t0, who, None, None))

        # ---- monthly invoices, one per supplier and register, a line per docket
        for register, supplier in (("concrete", sup_name), ("reo", ref.REO_SUPPLIER[1])):
            mine = [d for d in dockets if d[2] == job and d[3] == register]
            for month in sorted({(d[5].year, d[5].month) for d in mine}):
                if month == (today.year, today.month):
                    continue                                     # this month is delivered, not yet invoiced
                rows = [d for d in mine if (d[5].year, d[5].month) == month]
                inv_date = _month_end(date(*month, 1))
                overcharge = (job == ref.SEEDED["msr_rate_overcharge"]["project"] and register == "concrete"
                              and month == (2026, 6))
                inv_id = f"INV-{len(invoices) + 1:04d}"
                lines = []
                for d in rows:
                    rate = price_at(prices, job, supplier, d[6], rise if overcharge else d[5])
                    lines.append([d[4], f"{d[6]} delivered {d[5].strftime('%d/%m/%Y')}", d[7], rate, rhu(d[7] * rate, 100)])
                if job == ref.SEEDED["msr_unmatched_docket"]["project"] and register == "concrete" and month == (2026, 10):
                    rate = price_at(prices, job, supplier, "N32/20", inv_date)
                    lines.append(["RLC-779999", "N32/20 delivered 22/10/2026", 620, rate, rhu(620 * rate, 100)])
                if job == ref.SEEDED["msr_waiting_time"]["project"] and register == "concrete" and month == (2026, 9):
                    lines.append(["", "Waiting time", 200, 4500, 9000])
                if job == "2418" and register == "concrete" and month == (2026, 8):
                    sat = sum(d[7] for d in rows[:2])            # a listed surcharge, charged correctly: stays green
                    lines.append(["", "Saturday delivery", sat, 1800, rhu(sat * 1800, 100)])
                no = f"{'SI' if register == 'reo' else sup_code}-INV-{month[0] % 100}{month[1]:02d}-{job}"
                invoices.append([inv_id, job, register, supplier, no, inv_date, sum(ln[4] for ln in lines), None,
                                 0, 0, 0, "", datetime.combine(inv_date, datetime.min.time()) + timedelta(days=4, hours=10), who, None, None])
                inv_lines += [(inv_id, i, *ln, None, 0, "") for i, ln in enumerate(lines, start=1)]
        if job == ref.SEEDED["msr_duplicate_docket"]["project"]:
            # seeded: a short "adjustment" invoice that bills two August dockets a second time
            dup = [d for d in dockets if d[2] == job and d[3] == "concrete" and (d[5].year, d[5].month) == (2026, 8)][:2]
            inv_id = f"INV-{len(invoices) + 1:04d}"
            lines = []
            for d in dup:
                rate = price_at(prices, job, sup_name, d[6], d[5])
                lines.append([d[4], f"{d[6]} delivered {d[5].strftime('%d/%m/%Y')}", d[7], rate, rhu(d[7] * rate, 100)])
            inv_date = date(2026, 9, 18)
            invoices.append([inv_id, job, "concrete", sup_name, f"{sup_code}-ADJ-2609-{job}", inv_date, sum(ln[4] for ln in lines),
                             None, 0, 0, 0, "", datetime.combine(inv_date, datetime.min.time()) + timedelta(days=3, hours=10), who, None, None])
            inv_lines += [(inv_id, i, *ln, None, 0, "") for i, ln in enumerate(lines, start=1)]

    # ---- the inbox: paperwork received and not yet reviewed
    def doc(job: str, register: str, kind: str, supplier: str, payload: dict[str, Any]) -> None:
        doc_id = f"DOC-{len(docs) + 1:04d}"
        docs.append({"doc_id": doc_id, "project_id": job, "register": register, "kind": kind, "supplier": supplier,
                     "filename": f"{supplier.lower().replace(' ', '-')}-{kind}-{doc_id.lower()}.pdf", "payload": payload})

    for job, pours in sorted(pending_pours.items()):
        for did, register, supplier, code, item, when, planned, label in pours[:2]:
            docket_seq[code] += rng.randint(1, 9)
            no = f"{code}-{docket_seq[code]}" if code != "SFR" else f"BS-{docket_seq[code]:04d}"
            qty = min(planned, 720) if register == "concrete" else planned
            doc(job, register, "docket", supplier, {"docket_no": no, "date": when.isoformat(), "job": job, "item": item,
                                                    "qty_x100": qty, "pour": label, "delivery_id": did})
    job = "2440"   # a one-off supplier with no parser: the AI fallback's case
    doc(job, "concrete", "docket", ref.UNKNOWN_SUPPLIER[1], {"docket_no": "HV-9931", "date": (today - timedelta(days=4)).isoformat(),
                                                             "job": job, "item": "N32/20", "qty_x100": 480, "pour": "Blinding to footings"})
    # a quote: next year's rates, to be reviewed into the price list
    doc("2418", "concrete", "quote", "Coastal Premix", {"quote_no": "CPM-Q-2711", "date": (today - timedelta(days=3)).isoformat(),
                                                        "job": "2418", "effective_from": "2027-01-01",
                                                        "rates": [[i, rhu((r) * 10816, 10000)] for i, r in ref.CONCRETE_ITEMS],
                                                        "surcharges": [["Saturday delivery", "per m3", 1900], ["Waiting time", "per 15 min", 4800]]})
    # an invoice that arrived with those dockets: its lines stay unmatched until the dockets are confirmed
    billed = [d for d in docs if d["kind"] == "docket" and d["register"] == "concrete" and d["supplier"] != ref.UNKNOWN_SUPPLIER[1]]
    if billed:
        first = billed[0]
        same = [d for d in billed if d["project_id"] == first["project_id"]]
        lines = []
        for d in same:
            p = d["payload"]
            rate = price_at(prices, d["project_id"], d["supplier"], p["item"], date.fromisoformat(p["date"]))
            lines.append([p["docket_no"], f"{p['item']} delivered {date.fromisoformat(p['date']).strftime('%d/%m/%Y')}",
                          p["qty_x100"], rate, rhu(p["qty_x100"] * rate, 100)])
        code = next(c for c, n in ref.CONCRETE_SUPPLIERS if n == first["supplier"])
        doc(first["project_id"], "concrete", "invoice", first["supplier"],
            {"invoice_no": f"{code}-INV-2611A-{first['project_id']}", "date": (today - timedelta(days=2)).isoformat(),
             "job": first["project_id"], "lines": lines})

    # ---- a supplier that publishes through an API: Coastal Premix puts its
    # dockets and its tax invoice there. The dockets were also emailed (they are
    # in the inbox above); the invoice was not. A sync saves the invoice and
    # recognises the dockets, so nothing is recorded twice.
    feed = []
    published = ref.DEMO_NOW - timedelta(hours=20)
    api_dockets = [d for d in docs if d["supplier"] == ref.FEED_SUPPLIER and d["kind"] == "docket"]
    for d in api_dockets:
        p = d["payload"]
        feed.append((f"API-{p['docket_no']}", d["supplier"], d["project_id"], d["register"], "docket",
                     f"docket-{p['docket_no']}.pdf", published, d["kind"], p))
    for job in sorted({d["project_id"] for d in api_dockets}):
        mine = [d["payload"] for d in api_dockets if d["project_id"] == job]
        lines = []
        for p in mine:
            rate = price_at(prices, job, ref.FEED_SUPPLIER, p["item"], date.fromisoformat(p["date"]))
            lines.append([p["docket_no"], f"{p['item']} delivered {date.fromisoformat(p['date']).strftime('%d/%m/%Y')}",
                          p["qty_x100"], rate, rhu(p["qty_x100"] * rate, 100)])
        code = next(c for c, n in ref.CONCRETE_SUPPLIERS if n == ref.FEED_SUPPLIER)
        number = f"{code}-INV-2611B-{job}"
        feed.append((f"API-{number}", ref.FEED_SUPPLIER, job, "concrete", "invoice", f"invoice-{number}.pdf", published, "invoice",
                     {"invoice_no": number, "date": (today - timedelta(days=1)).isoformat(), "job": job, "lines": lines}))

    _ins(con, "msr_enrolment", enrol)
    _ins(con, "msr_budget_line", budget)
    _ins(con, "msr_price", prices)
    _ins(con, "msr_delivery", deliveries)
    _ins(con, "msr_docket", dockets)
    _ins(con, "msr_invoice", [tuple(i) for i in invoices])
    _ins(con, "msr_invoice_line", inv_lines)
    from src.app.services import supplier_docs   # the same renderers the app uses
    received = ref.DEMO_NOW - timedelta(days=1)
    con.executemany("""INSERT INTO msr_document (doc_id, project_id, register, kind, supplier, filename, status, received_at,
                                                 received_by, committed_ref, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [(d["doc_id"], d["project_id"], d["register"], d["kind"], d["supplier"], d["filename"],
                      "inbox", received, "Mailbox import", None, "email") for d in docs])
    _ins(con, "supplier_feed", [(r, s, j, reg, k, f, at, supplier_docs.render(kind, s, payload))
                                for r, s, j, reg, k, f, at, kind, payload in feed])
    _ins(con, "msr_document_blob", [(d["doc_id"], supplier_docs.render(d["kind"], d["supplier"], d["payload"])) for d in docs])
    _audit(con, sorted(audit, key=lambda r: r[0]))
