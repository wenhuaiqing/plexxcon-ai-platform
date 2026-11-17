"""Bid Summary arithmetic and validation. The browser runs the same sums on
every keystroke (frontend/src/lib/bidCalc.js); the server's are the record."""

from __future__ import annotations

from typing import Any

from src.app.calc.money import rhu, to_cents, to_scaled
from src.app.pipeline import reference as ref


def _grid_total(rows: list[dict[str, Any]] | None) -> int:
    return sum(to_cents(r.get("amount")) for r in (rows or []) if str(r.get("amount") or "").strip() != "")


def totals(data: dict[str, Any]) -> dict[str, int]:
    margin = data.get("margin") or {}
    direct = _grid_total(data.get("direct"))
    indirect = _grid_total(data.get("indirect"))
    contingency_bp = to_scaled(margin.get("contingency_pct"), 100)
    margin_bp = to_scaled(margin.get("margin_pct"), 100)
    escalation = to_cents(margin.get("escalation"))
    contingency = rhu((direct + indirect) * contingency_bp, 10000)
    grand_total = direct + indirect + contingency + escalation
    margin_cents = rhu(grand_total * margin_bp, 10000)
    final_ex = grand_total + margin_cents
    gst = rhu(final_ex * ref.GST_BP, 10000)
    gba = to_scaled((data.get("project") or {}).get("gross_building_area"), 1)
    return {
        "direct_cents": direct, "indirect_cents": indirect, "contingency_bp": contingency_bp,
        "contingency_cents": contingency, "escalation_cents": escalation, "grand_total_cents": grand_total,
        "margin_bp": margin_bp, "margin_cents": margin_cents, "final_ex_cents": final_ex, "gst_cents": gst,
        "final_inc_cents": final_ex + gst, "gross_building_area_m2": gba,
        "rate_per_m2_cents": rhu(final_ex, gba) if gba > 0 else 0,
    }


def _field(data: dict[str, Any], key: str) -> Any:
    for section in ("project", "programme"):
        block = data.get(section) or {}
        if key in block:
            return block[key]
    return None


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def validate(data: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Two tiers: hard stops block a submission; soft warnings ask first."""
    hard = [{"field": k, "label": label} for k, label in ref.BID_HARD_STOPS if _blank(_field(data, k))]
    gba = _field(data, "gross_building_area")
    if not _blank(gba):
        try:
            if to_scaled(gba, 1) <= 0:
                hard.append({"field": "gross_building_area", "label": "Gross Building Area"})
        except ValueError:
            hard.append({"field": "gross_building_area", "label": "Gross Building Area"})
    soft = [{"field": k, "label": label} for k, label in ref.BID_SOFT_WARNINGS if _blank(_field(data, k))]
    return {"hard": hard, "soft": soft}


def blank() -> dict[str, Any]:
    return {
        "project": {"bid_name": "", "bid_number": "", "sector": "", "client": "", "location": "",
                    "gross_building_area": "", "bid_gate": "", "estimator": ""},
        "programme": {"submission_date": "", "contract_execution": "", "site_establishment": "",
                      "practical_completion": "", "included_delays": ""},
        "direct": [], "indirect": [],
        "margin": {"contingency_pct": "", "margin_pct": "", "escalation": ""},
        "competitors": [], "benchmarking": {"comparable": "", "notes": ""},
    }
