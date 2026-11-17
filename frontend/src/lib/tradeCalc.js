// Trade Planner arithmetic for the instant preview - the same as
// backend/src/app/calc/trade.py. The Library tab runs both engines over the
// same scopes and shows whether they agree, case by case.
import { ceilDiv, rhu, safe, toCents, toScaled } from "./money.js";

const MODIFIER_KEYS = ["access", "complexity", "crew_mix", "handling"];
export const ROLE_RATE = { Supervisor: "Supervisor", "Leading hand": "Leading hand", "Safety adviser": "Supervisor", "Traffic controller": "Labourer" };

// Dates as plain y-m-d, counted in UTC so no timezone moves a day.
function parse(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}/.test(String(iso))) return null;
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}
const DAY = 86_400_000;
const iso = (ms) => new Date(ms).toISOString().slice(0, 10);

function isWorking(ms, saturdays, holidays) {
  if (holidays.has(iso(ms))) return false;
  const wd = new Date(ms).getUTCDay(); // 0 Sunday
  return (wd >= 1 && wd <= 5) || (wd === 6 && saturdays);
}

function firstWorking(ms, saturdays, holidays) {
  while (!isWorking(ms, saturdays, holidays)) ms += DAY;
  return ms;
}

function addWorking(start, days, saturdays, holidays) {
  let ms = firstWorking(start, saturdays, holidays);
  let left = Math.max(days - 1, 0);
  while (left > 0) {
    ms += DAY;
    if (isWorking(ms, saturdays, holidays)) left -= 1;
  }
  return ms;
}

export function modifierX10000(mods) {
  let product = 1;
  for (const k of MODIFIER_KEYS) product *= Math.max(Math.min(Number((mods || {})[k] || 100), 150), 10);
  return rhu(product, 10000);
}

export function locationCodes(job, locations) {
  const out = [];
  for (const loc of locations || []) {
    const zone = (String(loc.zone || "A").trim().toUpperCase() || "A").slice(0, 4);
    const levels = [];
    for (let b = Number(loc.basements || 0); b > 0; b -= 1) levels.push([`B${b}`, `Basement ${b}`]);
    if (Number(loc.grounds || 0) > 0) levels.push(["GF", "Ground"]);
    for (let n = 1; n <= Number(loc.levels || 0); n += 1) levels.push([`L${String(n).padStart(2, "0")}`, `Level ${n}`]);
    for (const [code, label] of levels) out.push({ code: `${job}-${zone}-${code}`, label: `Zone ${zone} - ${label}` });
  }
  return out;
}

export function calculate(scope, rates, ref) {
  const labourRates = ref.labour_rates;
  const holidays = new Set(ref.holidays);
  const project = scope.project || {};
  const job = String(project.project_id || "");
  const hpd = Math.max(safe(() => toScaled(project.hours_per_day || 8, 10), 80), 10);
  const sat = Boolean(project.work_saturdays);
  const targetFinish = parse(project.target_finish);
  const mobs = Object.fromEntries((project.mobilisations || []).map((m) => [String(m.id), m]));
  const ordinary = Math.min(hpd, ref.ordinary_hours_x10);
  const ot15 = Math.min(hpd - ordinary, ref.overtime_first_hours_x10);
  const codes = Object.fromEntries(Object.entries(rates));
  const trades = [];
  const tasks = [];
  for (const trade of scope.trades || []) {
    const name = String(trade.trade || "");
    const code = (ref.trades.find((x) => x.trade === name) || {}).code || name.slice(0, 3).toUpperCase();
    const crew = Math.max(Number(trade.crew_size || 0), 0);
    const cls = trade.classification || "Tradesperson";
    const rate = Number(labourRates[cls] ?? labourRates.Tradesperson);
    let hours = 0;
    (trade.tasks || []).forEach((task, i) => {
      const lib = codes[String(task.rate_code || "")];
      if (!lib) return;
      const qty = safe(() => toScaled(task.quantity, 100));
      const mod = modifierX10000(task.modifiers);
      const h = lib.rate_x1000 > 0 && mod > 0 ? rhu(qty * 1000 * 10000, lib.rate_x1000 * mod) : 0;
      hours += h;
      const location = String(task.location || "");
      tasks.push({ trade: name, seq: i + 1, location, cost_code: `${location || job}-${code}`, task: lib.task, unit: lib.unit, quantity_x100: qty, modifier_x10000: mod, hours_x100: h });
    });
    const mob = mobs[String(trade.mobilisation_id || "")];
    const start = parse((mob || {}).start) ?? parse(project.target_start);
    const capacity = crew * hpd * 10;
    const workDays = capacity > 0 && hours > 0 ? ceilDiv(hours, capacity) : 0;
    const startDay = start != null ? firstWorking(start, sat, holidays) : null;
    const finish = startDay != null ? addWorking(startDay, workDays, sat, holidays) : null;
    const ordH = rhu(hours * ordinary, hpd);
    const ot15H = rhu(hours * ot15, hpd);
    const ot20H = hours - ordH - ot15H;
    const labour = rhu(ordH * rate, 100) + rhu(ot15H * rate * 15, 1000) + rhu(ot20H * rate * 2, 100);
    trades.push({
      trade: name, trade_code: code, mobilisation: (mob || {}).name || "", classification: cls, crew_size: crew, hours_x100: hours,
      ordinary_hours_x100: ordH, overtime_hours_x100: ot15H + ot20H, work_days: workDays,
      start_date: startDay != null ? iso(startDay) : null, finish_date: finish != null ? iso(finish) : null,
      target_finish: targetFinish != null ? iso(targetFinish) : null,
      on_time: Boolean(finish != null && targetFinish != null && finish <= targetFinish), labour_cents: labour,
    });
  }
  const np = scope.non_production || {};
  const npRows = [];
  let npCents = 0;
  let npHours = 0;
  if (!np.waived) {
    for (const role of np.roles || []) {
      const count = Number(role.count || 0);
      const weeks = Number(role.weeks || 0);
      const r = Number(labourRates[ROLE_RATE[String(role.role)] || "Labourer"]);
      const h = count * weeks * 5 * hpd * 10;
      const cost = rhu(h * r, 100);
      npRows.push({ role: role.role, count, weeks, hours_x100: h, cost_cents: cost });
      npCents += cost;
      npHours += h;
    }
  }
  const fin = scope.financials || {};
  const materials = (fin.materials || []).reduce((s, m) => s + safe(() => toCents(m.amount)), 0);
  const plant = (fin.plant || []).reduce((s, p) => s + rhu(safe(() => toCents(p.rate_per_week)) * safe(() => toScaled(p.weeks, 10)), 10), 0);
  const spans = trades.filter((x) => x.start_date && x.finish_date && x.work_days > 0)
    .map((x) => [parse(x.start_date), parse(x.finish_date), x.crew_size]);
  let peak = 0;
  for (const edge of [...new Set(spans.map((s) => s[0]))].sort((a, b) => a - b)) {
    peak = Math.max(peak, spans.filter(([s, f]) => s <= edge && edge <= f).reduce((a, s) => a + s[2], 0));
  }
  const finishes = trades.filter((x) => x.finish_date && x.work_days > 0).map((x) => x.finish_date).sort();
  const finishDate = finishes.length ? finishes[finishes.length - 1] : null;
  const labourTotal = trades.reduce((s, x) => s + x.labour_cents, 0);
  return {
    trades, tasks, non_production: npRows,
    total_hours_x100: trades.reduce((s, x) => s + x.hours_x100, 0), non_production_hours_x100: npHours,
    labour_cents: labourTotal, non_production_cents: npCents, materials_cents: materials, plant_cents: plant,
    total_cents: labourTotal + npCents + materials + plant, peak_crew: peak, finish_date: finishDate,
    target_finish: targetFinish != null ? iso(targetFinish) : null,
    on_time: Boolean(finishDate && targetFinish != null && finishDate <= iso(targetFinish)), hours_per_day_x10: hpd,
  };
}

export function missing(scope, rates) {
  const out = [];
  const p = scope.project || {};
  const s = parse(p.target_start);
  const f = parse(p.target_finish);
  if (!p.project_id || s == null || f == null || f < s) out.push("Project");
  if (!(p.mobilisations || []).length || (p.mobilisations || []).some((m) => parse(m.start) == null)) out.push("Mobilisations");
  if (!locationCodes(String(p.project_id || ""), scope.locations).length) out.push("Locations");
  const mobIds = new Set((p.mobilisations || []).map((m) => String(m.id)));
  let ok = (scope.trades || []).length > 0;
  for (const tr of scope.trades || []) {
    if (!(tr.tasks || []).length || Number(tr.crew_size || 0) <= 0 || !mobIds.has(String(tr.mobilisation_id))) ok = false;
    for (const task of tr.tasks || []) {
      if (safe(() => toScaled(task.quantity, 100)) <= 0 || !rates[String(task.rate_code)] || !task.location) ok = false;
    }
  }
  if (!ok) out.push("Trades & tasks");
  const np = scope.non_production || {};
  if (!np.waived && !(np.roles || []).length) out.push("Non-production roles");
  return out;
}

// Parity: the fields both engines must agree on exactly.
export const PARITY_FIELDS = ["total_hours_x100", "labour_cents", "non_production_cents", "materials_cents", "plant_cents", "total_cents", "peak_crew", "finish_date"];
