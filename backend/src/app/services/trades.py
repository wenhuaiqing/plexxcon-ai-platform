"""Trade Planner: a structured trades and labour request for a job, reviewed
by someone other than its author.

The browser calculates on every keystroke for the preview; the numbers stored
are always the server's, recalculated from the scope at save. A decision needs
feedback, and nobody decides their own request - both enforced here, not in
the page. A job can hold several accepted requests: a base and its top-ups.

Not here yet, on purpose: budget against actuals (it needs the project
management feed), and task dependencies (this is a feasibility check, not a
critical-path programme).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from src.app.calc import trade as calc
from src.app.pipeline import reference as ref
from src.app.pipeline.generate import request_rows
from src.app.services import audit, db

SYSTEM = "trade_planner"
DECISIONS = {"accepted": "Accepted", "rejected": "Rejected", "tentative": "Tentative"}


def library() -> list[dict]:
    return db.rows("""SELECT rate_code, trade, trade_code, task, unit, rate_x1000, rate_x1000 / 1000.0 AS rate,
                             default_crew, updated_at, updated_by FROM tp_rate ORDER BY trade, rate_code""")


def _rates() -> dict[str, dict[str, Any]]:
    return {r["rate_code"]: r for r in db.raw("SELECT rate_code, trade, task, unit, rate_x1000 FROM tp_rate")}


def reference() -> dict[str, Any]:
    return {
        "library": library(),
        "trades": [{"trade": t, "code": c} for t, c, _ in ref.TRADES],
        "labour_rates": ref.LABOUR_RATES, "modifiers": ref.MODIFIERS,
        "non_production_roles": ref.NON_PRODUCTION_ROLES, "role_rate": calc.ROLE_RATE,
        "holidays": [h.isoformat() for h in ref.QLD_HOLIDAYS],
        "ordinary_hours_x10": ref.ORDINARY_HOURS_X10, "overtime_first_hours_x10": ref.OVERTIME_FIRST_HOURS_X10,
        "projects": db.rows("SELECT project_id, name, sector, start_date, end_date FROM project WHERE status = 'active' ORDER BY project_id"),
        "people": ref.PEOPLE["supervisors"] + ref.PEOPLE["managers"],
        "today": ref.DEMO_TODAY.isoformat(),
    }


def calculate(scope: dict[str, Any]) -> dict[str, Any]:
    rates = _rates()
    result = calc.calculate(scope, rates)
    result["missing"] = calc.validate_scope(scope, rates)
    result["locations"] = calc.location_codes(str((scope.get("project") or {}).get("project_id") or ""), scope.get("locations"))
    return result


HEAD = """request_id, root_request_id, version, project_id, title, q.status AS status, author, created_at, updated_at, submitted_at,
          reviewer, reviewed_at, feedback, total_hours_x100, labour_cents, non_production_cents, materials_cents,
          plant_cents, total_cents, peak_crew, target_finish, finish_date, on_time"""


def requests(actor: str = "") -> list[dict]:
    # A draft is private to its author.
    return db.rows(f"""SELECT {HEAD}, p.name AS project_name FROM tp_request q JOIN project p USING (project_id)
                       WHERE q.status <> 'draft' OR q.author = ?
                       ORDER BY CASE q.status WHEN 'pending' THEN 0 WHEN 'tentative' THEN 1 WHEN 'draft' THEN 2 ELSE 3 END,
                                q.updated_at DESC""", [actor])


def request(request_id: str) -> dict[str, Any]:
    found = db.rows(f"SELECT {HEAD}, data_json, p.name AS project_name FROM tp_request q JOIN project p USING (project_id) WHERE q.request_id = ?",
                    [request_id])
    if not found:
        raise HTTPException(status_code=404, detail="No such request.")
    head = found[0]
    scope = json.loads(head.pop("data_json"))
    versions = db.rows("""SELECT request_id, version, status, author, submitted_at, reviewer, feedback, total_cents / 100.0 AS total
                          FROM tp_request WHERE root_request_id = ? ORDER BY version""", [head["root_request_id"]])
    return {**head, "scope": scope, "result": calculate(scope), "versions": versions}


def jobs() -> list[dict]:
    """Accepted requests aggregate per job: the base scope plus its top-ups."""
    rows = db.rows("""
        SELECT q.project_id, p.name AS project_name, count(*) AS accepted_requests,
               sum(total_hours_x100) / 100.0 AS hours, sum(total_cents) / 100.0 AS budget, sum(labour_cents) / 100.0 AS labour,
               max(finish_date) AS finish_date, string_agg(request_id, ', ' ORDER BY submitted_at) AS requests
        FROM tp_request q JOIN project p USING (project_id) WHERE q.status = 'accepted'
        GROUP BY 1, 2 ORDER BY 1""")
    waiting = {r["project_id"]: r["n"] for r in db.rows(
        "SELECT project_id, count(*) AS n FROM tp_request WHERE status IN ('pending', 'tentative') GROUP BY 1")}
    for r in rows:
        r["awaiting_review"] = waiting.get(r["project_id"], 0)
    return rows


def parity_cases() -> list[dict[str, Any]]:
    """Scopes the browser recalculates with its own engine; the two must agree to the cent and the day."""
    rates = _rates()
    stored = db.raw("SELECT request_id, data_json FROM tp_request ORDER BY request_id")
    cases = [{"name": r["request_id"], "scope": json.loads(r["data_json"])} for r in stored]
    edge = json.loads(stored[0]["data_json"])
    for name, change in (("10-hour days, Saturdays worked", {"hours_per_day": "10", "work_saturdays": True}),
                         ("12-hour shutdown shifts", {"hours_per_day": "12"}),
                         ("7.6-hour days starting on a public holiday", {"hours_per_day": "7.6"})):
        scope = json.loads(json.dumps(edge))
        scope["project"].update(change)
        if "holiday" in name:
            scope["project"]["mobilisations"][0]["start"] = "2026-12-25"
        for trade in scope["trades"]:
            for task in trade["tasks"]:
                task["modifiers"] = {"access": 85, "complexity": 90, "crew_mix": 92, "handling": 76}
        cases.append({"name": name, "scope": scope})
    return [{**c, "expected": calc.calculate(c["scope"], rates)} for c in cases]


# ------------------------------------------------------------------ writes --
def _write(cur: Any, head: tuple, trades: list[tuple], tasks: list[tuple]) -> None:
    rid = head[0]
    cur.execute("DELETE FROM tp_request WHERE request_id = ?", [rid])
    cur.execute("DELETE FROM tp_request_trade WHERE request_id = ?", [rid])
    cur.execute("DELETE FROM tp_request_task WHERE request_id = ?", [rid])
    cur.execute(f"INSERT INTO tp_request VALUES ({', '.join('?' for _ in head)})", list(head))
    for t in trades:
        cur.execute(f"INSERT INTO tp_request_trade VALUES ({', '.join('?' for _ in t)})", list(t))
    for t in tasks:
        cur.execute(f"INSERT INTO tp_request_task VALUES ({', '.join('?' for _ in t)})", list(t))


def save(actor: str, request_id: str | None, title: str, scope: dict[str, Any], submit: bool) -> dict[str, Any]:
    rates = _rates()
    project_id = str((scope.get("project") or {}).get("project_id") or "")
    with db.writing() as cur:
        if not cur.execute("SELECT 1 FROM project WHERE project_id = ?", [project_id]).fetchone():
            raise HTTPException(status_code=422, detail="Choose a job before saving.")
        now = audit.now()
        if request_id:
            row = cur.execute("SELECT status, author, root_request_id, version, created_at FROM tp_request WHERE request_id = ?",
                              [request_id]).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No such request.")
            status, author, root, version, created = row
            if status != "draft":
                audit.refuse(cur, actor, SYSTEM, request_id, "edit request",
                             f"{request_id} is {status}; a submitted request is not edited. Load it as a revision instead.", project_id=project_id)
            if author != actor:
                audit.refuse(cur, actor, SYSTEM, request_id, "edit request",
                             f"This draft is private to {author}.", project_id=project_id, status=403)
        else:
            n = cur.execute("SELECT coalesce(max(CAST(substr(request_id, 4) AS INTEGER)), 0) + 1 FROM tp_request").fetchone()[0]
            request_id = f"TR-{n:04d}"
            root, version, created = request_id, 1, now
        if submit:
            missing = calc.validate_scope(scope, rates)
            if missing:
                audit.refuse(cur, actor, SYSTEM, request_id, "submit for approval",
                             "Complete first: " + ", ".join(missing) + ".", project_id=project_id, status=422)
        head, trades, tasks = request_rows(request_id, root, version, title.strip() or "Untitled request",
                                           "pending" if submit else "draft", actor, created, scope, rates)
        head = list(head)
        head[8], head[9] = now, (now if submit else None)
        _write(cur, tuple(head), trades, tasks)
        audit.record(cur, actor, SYSTEM, request_id, "submit for approval" if submit else "save draft",
                     project_id=project_id, detail=title)
    return request(request_id)


def revise(actor: str, request_id: str) -> dict[str, Any]:
    """Load a revision: a new draft, one version on, starting from this one's scope."""
    with db.writing() as cur:
        row = cur.execute("SELECT root_request_id, title, data_json, project_id, status FROM tp_request WHERE request_id = ?",
                          [request_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No such request.")
        root, title, data, project_id, status = row
        if status == "draft":
            raise HTTPException(status_code=409, detail="That request is still a draft. Resume it instead.")
        version = cur.execute("SELECT max(version) + 1 FROM tp_request WHERE root_request_id = ?", [root]).fetchone()[0]
        n = cur.execute("SELECT coalesce(max(CAST(substr(request_id, 4) AS INTEGER)), 0) + 1 FROM tp_request").fetchone()[0]
        new_id = f"TR-{n:04d}"
        head, trades, tasks = request_rows(new_id, root, version, title, "draft", actor, audit.now(), json.loads(data), _rates())
        _write(cur, head, trades, tasks)
        audit.record(cur, actor, SYSTEM, new_id, "load revision", project_id=project_id,
                     detail=f"Version {version}, from {request_id}")
    return request(new_id)


def review(actor: str, request_id: str, decision: str, feedback: str) -> dict[str, Any]:
    with db.writing() as cur:
        row = cur.execute("SELECT status, author, project_id, title FROM tp_request WHERE request_id = ?", [request_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No such request.")
        status, author, project_id, title = row
        action = f"review: {decision}"
        if decision not in DECISIONS:
            raise HTTPException(status_code=422, detail="Decision must be accepted, rejected or tentative.")
        if status not in ("pending", "tentative"):
            audit.refuse(cur, actor, SYSTEM, request_id, action, f"{request_id} is {status}; only a pending or tentative request can be decided.",
                         project_id=project_id)
        if author == actor:
            audit.refuse(cur, actor, SYSTEM, request_id, action,
                         "You cannot decide your own request. It needs a second person.", project_id=project_id, status=403)
        if not feedback.strip():
            audit.refuse(cur, actor, SYSTEM, request_id, action, "Feedback is mandatory for any decision.", project_id=project_id, status=422)
        now = audit.now()
        cur.execute("UPDATE tp_request SET status = ?, reviewer = ?, reviewed_at = ?, feedback = ?, updated_at = ? WHERE request_id = ?",
                    [decision, actor, now, feedback.strip()[:600], now, request_id])
        audit.record(cur, actor, SYSTEM, request_id, action, project_id=project_id, detail=title, reason=feedback.strip()[:400])
    return request(request_id)


def update_rate(actor: str, rate_code: str, rate: Any, reason: str) -> dict[str, Any]:
    from src.app.calc.money import to_scaled
    with db.writing() as cur:
        row = cur.execute("SELECT rate_x1000, task, unit FROM tp_rate WHERE rate_code = ?", [rate_code]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No such rate.")
        try:
            new = to_scaled(rate, 1000)
        except ValueError:
            new = 0
        if new <= 0:
            audit.refuse(cur, actor, SYSTEM, rate_code, "change library rate", "A production rate must be a number above zero.", status=422)
        if not reason.strip():
            audit.refuse(cur, actor, SYSTEM, rate_code, "change library rate",
                         "Say why the rate is changing: every task on every job draws from this library.", status=422)
        cur.execute("UPDATE tp_rate SET rate_x1000 = ?, updated_at = ?, updated_by = ? WHERE rate_code = ?", [new, audit.now(), actor, rate_code])
        audit.record(cur, actor, SYSTEM, rate_code, "change library rate",
                     detail=f"{row[1]}: {row[0] / 1000:g} to {new / 1000:g} {row[2]} per worker-hour", reason=reason.strip()[:300])
    return {"rate_code": rate_code, "rate_x1000": new}


def audit_log() -> list[dict]:
    return db.rows("""SELECT ts, actor, project_id, subject, action, outcome, detail, reason FROM audit_log
                      WHERE system = ? ORDER BY audit_id DESC LIMIT 300""", [SYSTEM])
