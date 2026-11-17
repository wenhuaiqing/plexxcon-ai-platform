// Bid Summary sums on every keystroke - the same as backend/src/app/calc/bid.py.
import { rhu, safe, toCents, toScaled } from "./money.js";

const GST_BP = 1000;

function gridTotal(rows) {
  return (rows || []).reduce((s, r) => s + (String(r.amount ?? "").trim() === "" ? 0 : safe(() => toCents(r.amount))), 0);
}

export function totals(data) {
  const m = data.margin || {};
  const direct = gridTotal(data.direct);
  const indirect = gridTotal(data.indirect);
  const contingencyBp = safe(() => toScaled(m.contingency_pct, 100));
  const marginBp = safe(() => toScaled(m.margin_pct, 100));
  const escalation = safe(() => toCents(m.escalation));
  const contingency = rhu((direct + indirect) * contingencyBp, 10000);
  const grand = direct + indirect + contingency + escalation;
  const margin = rhu(grand * marginBp, 10000);
  const finalEx = grand + margin;
  const gst = rhu(finalEx * GST_BP, 10000);
  const gba = safe(() => toScaled((data.project || {}).gross_building_area, 1));
  return {
    direct_cents: direct, indirect_cents: indirect, contingency_cents: contingency, escalation_cents: escalation,
    grand_total_cents: grand, margin_bp: marginBp, margin_cents: margin, final_ex_cents: finalEx, gst_cents: gst,
    final_inc_cents: finalEx + gst, gross_building_area_m2: gba, rate_per_m2_cents: gba > 0 ? rhu(finalEx, gba) : 0,
  };
}

function field(data, key) {
  for (const s of ["project", "programme"]) if ((data[s] || {})[key] !== undefined) return data[s][key];
  return undefined;
}

export function validate(data, hardStops, softWarnings) {
  const blank = (v) => v == null || String(v).trim() === "";
  const hard = hardStops.filter((f) => blank(field(data, f.field)));
  const gba = field(data, "gross_building_area");
  if (!blank(gba) && safe(() => toScaled(gba, 1), 0) <= 0 && !hard.some((h) => h.field === "gross_building_area")) {
    hard.push(hardStops.find((f) => f.field === "gross_building_area"));
  }
  return { hard, soft: softWarnings.filter((f) => blank(field(data, f.field))) };
}
