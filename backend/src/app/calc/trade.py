"""Trade Planner arithmetic: what work, at what production rate, with what
crew, giving what hours, at what cost, finishing when.

A labour budget and feasibility check, not a critical-path scheduler: each
trade runs from its mobilisation start by working-day arithmetic; there are no
task dependencies. Integers throughout. frontend/src/lib/tradeCalc.js is the
same arithmetic for the instant preview, and the parity cases prove it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from src.app.calc.money import ceil_div, rhu, to_cents, to_scaled
from src.app.pipeline import reference as ref

MODIFIER_KEYS = ["access", "complexity", "crew_mix", "handling"]
ROLE_RATE = {"Supervisor": "Supervisor", "Leading hand": "Leading hand", "Safety adviser": "Supervisor",
             "Traffic controller": "Labourer"}


def _d(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def is_working_day(day: date, work_saturdays: bool, holidays: set[date]) -> bool:
    if day in holidays:
        return False
    weekday = day.weekday()
    return weekday < 5 or (weekday == 5 and work_saturdays)


def first_working_day(day: date, work_saturdays: bool, holidays: set[date]) -> date:
    while not is_working_day(day, work_saturdays, holidays):
        day += timedelta(days=1)
    return day


def add_working_days(start: date, days: int, work_saturdays: bool, holidays: set[date]) -> date:
    """The date of the nth working day counting start as day one."""
    day = first_working_day(start, work_saturdays, holidays)
    remaining = max(days - 1, 0)
    while remaining > 0:
        day += timedelta(days=1)
        if is_working_day(day, work_saturdays, holidays):
            remaining -= 1
    return day


def modifier_x10000(modifiers: dict[str, Any] | None) -> int:
    product = 1
    for key in MODIFIER_KEYS:
        pct = int((modifiers or {}).get(key) or 100)
        product *= max(min(pct, 150), 10)
    return rhu(product, 10000)


def task_hours_x100(quantity_x100: int, rate_x1000: int, mod_x10000: int) -> int:
    if rate_x1000 <= 0 or mod_x10000 <= 0:
        return 0
    return rhu(quantity_x100 * 1000 * 10000, rate_x1000 * mod_x10000)


def location_codes(job: str, locations: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Locations entered once; the cost-code stems come from them."""
    out: list[dict[str, str]] = []
    for loc in locations or []:
        zone = (str(loc.get("zone") or "A").strip().upper() or "A")[:4]
        levels: list[tuple[str, str]] = []
        for b in range(int(loc.get("basements") or 0), 0, -1):
            levels.append((f"B{b}", f"Basement {b}"))
        if int(loc.get("grounds") or 0) > 0:
            levels.append(("GF", "Ground"))
        for n in range(1, int(loc.get("levels") or 0) + 1):
            levels.append((f"L{n:02d}", f"Level {n}"))
        for code, label in levels:
            out.append({"code": f"{job}-{zone}-{code}", "label": f"Zone {zone} - {label}"})
    return out


def calculate(scope: dict[str, Any], rates: dict[str, dict[str, Any]],
              labour_rates: dict[str, int] | None = None, holidays: list[date] | None = None) -> dict[str, Any]:
    labour_rates = labour_rates or ref.LABOUR_RATES
    holiday_set = set(holidays if holidays is not None else ref.QLD_HOLIDAYS)
    project = scope.get("project") or {}
    job = str(project.get("project_id") or "")
    hpd = max(int(to_scaled(project.get("hours_per_day") or 8, 10)), 10)
    saturdays = bool(project.get("work_saturdays"))
    target_finish = _d(project.get("target_finish"))
    mobilisations = {str(m.get("id")): m for m in (project.get("mobilisations") or [])}

    ordinary = min(hpd, ref.ORDINARY_HOURS_X10)
    overtime = hpd - ordinary
    ot15 = min(overtime, ref.OVERTIME_FIRST_HOURS_X10)

    trades_out: list[dict[str, Any]] = []
    tasks_out: list[dict[str, Any]] = []
    for trade in scope.get("trades") or []:
        name = str(trade.get("trade") or "")
        code = next((c for t, c, _ in ref.TRADES if t == name), name[:3].upper())
        crew = max(int(trade.get("crew_size") or 0), 0)
        classification = trade.get("classification") or "Tradesperson"
        rate_cents = int(labour_rates.get(classification, labour_rates["Tradesperson"]))
        hours = 0
        for seq, task in enumerate(trade.get("tasks") or [], start=1):
            lib = rates.get(str(task.get("rate_code") or ""))
            if not lib:
                continue
            qty = to_scaled(task.get("quantity"), 100)
            mod = modifier_x10000(task.get("modifiers"))
            h = task_hours_x100(qty, int(lib["rate_x1000"]), mod)
            hours += h
            location = str(task.get("location") or "")
            tasks_out.append({
                "trade": name, "seq": seq, "location": location,
                "cost_code": f"{location or job}-{code}", "task": lib["task"], "rate_code": lib["rate_code"],
                "unit": lib["unit"], "quantity_x100": qty, "rate_x1000": int(lib["rate_x1000"]),
                "modifier_x10000": mod, "hours_x100": h,
            })
        mob = mobilisations.get(str(trade.get("mobilisation_id") or ""))
        start = _d((mob or {}).get("start")) or _d(project.get("target_start"))
        capacity = crew * hpd * 10
        work_days = ceil_div(hours, capacity) if capacity > 0 and hours > 0 else 0
        start_day = first_working_day(start, saturdays, holiday_set) if start else None
        finish = add_working_days(start_day, work_days, saturdays, holiday_set) if start_day else None
        ord_h = rhu(hours * ordinary, hpd)
        ot15_h = rhu(hours * ot15, hpd)
        ot20_h = hours - ord_h - ot15_h
        labour = rhu(ord_h * rate_cents, 100) + rhu(ot15_h * rate_cents * 15, 1000) + rhu(ot20_h * rate_cents * 2, 100)
        trades_out.append({
            "trade": name, "trade_code": code, "mobilisation": (mob or {}).get("name") or "",
            "classification": classification, "crew_size": crew, "hours_x100": hours,
            "ordinary_hours_x100": ord_h, "overtime_hours_x100": ot15_h + ot20_h, "work_days": work_days,
            "start_date": start_day.isoformat() if start_day else None,
            "finish_date": finish.isoformat() if finish else None,
            "target_finish": target_finish.isoformat() if target_finish else None,
            "on_time": bool(finish and target_finish and finish <= target_finish),
            "labour_cents": labour,
        })

    non_production = scope.get("non_production") or {}
    np_rows, np_cents, np_hours = [], 0, 0
    if not non_production.get("waived"):
        for role in non_production.get("roles") or []:
            count, weeks = int(role.get("count") or 0), int(role.get("weeks") or 0)
            rate = int(labour_rates[ROLE_RATE.get(str(role.get("role")), "Labourer")])
            h = count * weeks * 5 * hpd * 10
            cost = rhu(h * rate, 100)
            np_rows.append({"role": role.get("role"), "count": count, "weeks": weeks, "hours_x100": h, "cost_cents": cost})
            np_cents += cost
            np_hours += h

    financials = scope.get("financials") or {}
    materials = sum(to_cents(m.get("amount")) for m in financials.get("materials") or [])
    plant = sum(rhu(to_cents(p.get("rate_per_week")) * to_scaled(p.get("weeks"), 10), 10)
                for p in financials.get("plant") or [])

    spans = [(date.fromisoformat(t["start_date"]), date.fromisoformat(t["finish_date"]), t["crew_size"])
             for t in trades_out if t["start_date"] and t["finish_date"] and t["work_days"] > 0]
    peak = 0
    for edge in sorted({s for s, _, _ in spans}):
        peak = max(peak, sum(c for s, f, c in spans if s <= edge <= f))
    finishes = [t["finish_date"] for t in trades_out if t["finish_date"] and t["work_days"] > 0]
    finish_date = max(finishes) if finishes else None
    labour_total = sum(t["labour_cents"] for t in trades_out)
    return {
        "trades": trades_out, "tasks": tasks_out, "non_production": np_rows,
        "total_hours_x100": sum(t["hours_x100"] for t in trades_out), "non_production_hours_x100": np_hours,
        "labour_cents": labour_total, "non_production_cents": np_cents, "materials_cents": materials,
        "plant_cents": plant, "total_cents": labour_total + np_cents + materials + plant,
        "peak_crew": peak, "finish_date": finish_date,
        "target_finish": target_finish.isoformat() if target_finish else None,
        "on_time": bool(finish_date and target_finish and finish_date <= target_finish.isoformat()),
        "hours_per_day_x10": hpd,
    }


def validate_scope(scope: dict[str, Any], rates: dict[str, dict[str, Any]]) -> list[str]:
    """What the wizard's mandatory phase still needs, in the helper text's words."""
    missing: list[str] = []
    project = scope.get("project") or {}
    if not project.get("project_id") or not _d(project.get("target_start")) or not _d(project.get("target_finish")):
        missing.append("Project")
    elif _d(project["target_finish"]) < _d(project["target_start"]):
        missing.append("Project")
    if not project.get("mobilisations") or any(not _d(m.get("start")) for m in project.get("mobilisations") or []):
        missing.append("Mobilisations")
    if not location_codes(str(project.get("project_id") or ""), scope.get("locations")):
        missing.append("Locations")
    trades = scope.get("trades") or []
    mob_ids = {str(m.get("id")) for m in project.get("mobilisations") or []}
    ok = bool(trades)
    for trade in trades:
        tasks = trade.get("tasks") or []
        if (not tasks or int(trade.get("crew_size") or 0) <= 0 or str(trade.get("mobilisation_id")) not in mob_ids):
            ok = False
        for task in tasks:
            try:
                qty = to_scaled(task.get("quantity"), 100)
            except ValueError:
                qty = 0
            if qty <= 0 or str(task.get("rate_code")) not in rates or not task.get("location"):
                ok = False
    if not ok:
        missing.append("Trades & tasks")
    non_production = scope.get("non_production") or {}
    if not non_production.get("waived") and not non_production.get("roles"):
        missing.append("Non-production roles")
    return missing
