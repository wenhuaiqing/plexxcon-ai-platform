// Trade Planner: a guided wizard that builds a trades and labour request -
// what work, where, at what production rate, with what crew, giving what
// hours, within what budget, finishing when - then a second person decides it.

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, CheckCircle2, FilePlus2, GitBranch, History, Plus, RotateCcw, Save, Send, Trash2 } from "lucide-react";
import Drawer from "../../components/common/Drawer.jsx";
import { useTheme } from "../../context/ThemeContext.jsx";
import { actorName } from "../../config.js";
import { api, apiWrite, fmtAud, fmtDate, fmtDateTime, fmtInt, useApi } from "../../lib/api.js";
import { PARITY_FIELDS, calculate, locationCodes, missing } from "../../lib/tradeCalc.js";
import {
  Choice, Field, FormGrid, Input, MountedTabs, ReadOnlyNotice, canWrite, readLocal, useToast, writeLocal,
} from "../../lib/kit.jsx";
import {
  Badge, Button, CTAButton, Callout, Card, ErrorNote, Grid, KeyValues, Loading, PageHeader, SectionTitle, SegmentedControl, Stat, Table,
} from "../../lib/ui.jsx";
import { AuditTable } from "../BidSummary/BidSummary.jsx";

const LOCAL = "plexxcon-demo:trade-request-local";
const STATUS_TONE = { draft: "neutral", pending: "warning", tentative: "serious", accepted: "good", rejected: "critical" };
const hours = (x100) => (x100 / 100).toLocaleString("en-AU", { maximumFractionDigits: 1 });
const cents = (c) => fmtAud(c / 100);

function blankScope(today) {
  return {
    project: { project_id: "", target_start: "", target_finish: "", hours_per_day: "8", work_saturdays: false,
      mobilisations: [{ id: "M1", name: "Mobilisation 1", start: "" }] },
    locations: [{ zone: "A", basements: 0, grounds: 1, levels: 1, units_per_level: 0 }],
    trades: [], non_production: { waived: false, roles: [] }, financials: { materials: [], plant: [] }, advanced: false, _today: today,
  };
}

function useRates(reference) {
  return useMemo(() => Object.fromEntries((reference?.library || []).map((r) => [r.rate_code, r])), [reference]);
}

// -------------------------------------------------------------------- wizard --
function ScopeEditor({ scope, setScope, reference, rates, disabled }) {
  const { t } = useTheme();
  const p = scope.project;
  const setP = (k) => (v) => setScope({ ...scope, project: { ...p, [k]: v } });
  const codes = locationCodes(p.project_id, scope.locations);
  const setTrade = (i, patch) => setScope({ ...scope, trades: scope.trades.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
  const setTask = (i, k, patch) => setTrade(i, { tasks: scope.trades[i].tasks.map((x, j) => (j === k ? { ...x, ...patch } : x)) });
  const np = scope.non_production;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Card title="Project" hint="The job, its target window, working hours and the date tranches crews come on site.">
        <FormGrid>
          <Field label="Job"><Choice label="Job" disabled={disabled} value={p.project_id} onChange={setP("project_id")}
            options={[{ value: "", label: "Choose a job..." }, ...reference.projects.map((j) => ({ value: j.project_id, label: `${j.project_id} ${j.name}` }))]} /></Field>
          <Field label="Target start"><Input type="date" label="Target start" disabled={disabled} value={p.target_start} onChange={setP("target_start")} /></Field>
          <Field label="Target finish"><Input type="date" label="Target finish" disabled={disabled} value={p.target_finish} onChange={setP("target_finish")} /></Field>
          <Field label="Hours per day" hint="Over 8 is overtime: 2 hours at 1.5x, the rest at 2x"><Input label="Hours per day" disabled={disabled} value={p.hours_per_day} onChange={setP("hours_per_day")} /></Field>
          <Field label="Saturdays"><label style={{ fontSize: 13, display: "flex", gap: 6, alignItems: "center", paddingTop: 6 }}>
            <Input type="checkbox" label="Work Saturdays" disabled={disabled} value={undefined} checked={Boolean(p.work_saturdays)} onChange={setP("work_saturdays")} /> Work Saturdays</label></Field>
        </FormGrid>
        <div style={{ marginTop: 12, fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: t.textMuted }}>Mobilisations</div>
        {p.mobilisations.map((m, i) => (
          <div key={m.id} style={{ display: "flex", gap: 8, marginTop: 6, alignItems: "center", flexWrap: "wrap" }}>
            <Input label={`Mobilisation ${i + 1} name`} disabled={disabled} value={m.name} style={{ maxWidth: 220 }}
              onChange={(v) => setP("mobilisations")(p.mobilisations.map((x, j) => (j === i ? { ...x, name: v } : x)))} />
            <Input type="date" label={`Mobilisation ${i + 1} start`} disabled={disabled} value={m.start} style={{ maxWidth: 170 }}
              onChange={(v) => setP("mobilisations")(p.mobilisations.map((x, j) => (j === i ? { ...x, start: v } : x)))} />
            {!disabled && p.mobilisations.length > 1 && <Button icon={Trash2} onClick={() => setP("mobilisations")(p.mobilisations.filter((_, j) => j !== i))}>Remove</Button>}
          </div>
        ))}
        {!disabled && <div style={{ marginTop: 8 }}><Button icon={Plus} onClick={() => setP("mobilisations")([...p.mobilisations, { id: `M${Date.now() % 100000}`, name: `Mobilisation ${p.mobilisations.length + 1}`, start: "" }])}>Add a mobilisation</Button></div>}
      </Card>

      <Card title="Locations" hint="Entered once. The cost codes come from them, so nobody types a cost code by hand.">
        {scope.locations.map((loc, i) => (
          <FormGrid key={i} min={120}>
            {[["zone", "Zone"], ["basements", "Basements"], ["grounds", "Ground floors"], ["levels", "Levels"], ["units_per_level", "Units per level"]].map(([k, label]) => (
              <Field key={k} label={label}><Input label={`${label} ${i + 1}`} disabled={disabled} value={loc[k]}
                onChange={(v) => setScope({ ...scope, locations: scope.locations.map((x, j) => (j === i ? { ...x, [k]: k === "zone" ? v : v.replace(/\D/g, "") } : x)) })} /></Field>
            ))}
          </FormGrid>
        ))}
        {!disabled && <div style={{ marginTop: 8 }}><Button icon={Plus} onClick={() => setScope({ ...scope, locations: [...scope.locations, { zone: String.fromCharCode(65 + scope.locations.length), basements: 0, grounds: 0, levels: 1, units_per_level: 0 }] })}>Add a zone</Button></div>}
        <p style={{ fontSize: 12, color: t.textMuted, marginBottom: 0 }}>
          {codes.length ? <>Generated: {codes.slice(0, 8).map((c) => c.code).join(", ")}{codes.length > 8 ? ` and ${codes.length - 8} more` : ""}</> : "Choose a job to generate the codes."}
        </p>
      </Card>

      <Card title="Trades & tasks" hint="Each task takes a quantity and draws its production rate from the shared library." right={(
        <SegmentedControl label="Mode" value={scope.advanced ? "advanced" : "basic"} onChange={(v) => setScope({ ...scope, advanced: v === "advanced" })}
          options={[{ value: "basic", label: "Basic" }, { value: "advanced", label: "Advanced" }]} />
      )}>
        {scope.trades.map((tr, i) => {
          const lib = reference.library.filter((r) => r.trade === tr.trade);
          return (
            <div key={i} style={{ border: `1px solid ${t.border}`, borderRadius: 10, padding: 12, marginBottom: 10 }}>
              <FormGrid min={150}>
                <Field label="Trade"><Choice label={`Trade ${i + 1}`} disabled={disabled} value={tr.trade} onChange={(v) => setTrade(i, { trade: v, tasks: [] })}
                  options={reference.trades.map((x) => x.trade)} /></Field>
                <Field label="Mobilisation"><Choice label={`Trade ${i + 1} mobilisation`} disabled={disabled} value={tr.mobilisation_id} onChange={(v) => setTrade(i, { mobilisation_id: v })}
                  options={[{ value: "", label: "Choose..." }, ...p.mobilisations.map((m) => ({ value: m.id, label: m.name }))]} /></Field>
                <Field label="Crew"><Input label={`Trade ${i + 1} crew`} disabled={disabled} value={tr.crew_size} onChange={(v) => setTrade(i, { crew_size: v.replace(/\D/g, "") })} /></Field>
                <Field label="Classification"><Choice label={`Trade ${i + 1} classification`} disabled={disabled} value={tr.classification} onChange={(v) => setTrade(i, { classification: v })}
                  options={Object.keys(reference.labour_rates)} /></Field>
              </FormGrid>
              {tr.tasks.map((task, k) => (
                <div key={k} style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <Choice label={`Trade ${i + 1} task ${k + 1}`} disabled={disabled} value={task.rate_code} onChange={(v) => setTask(i, k, { rate_code: v })} style={{ flex: "2 1 200px" }}
                    options={[{ value: "", label: "Task from the library..." }, ...lib.map((r) => ({ value: r.rate_code, label: `${r.task} (${r.rate} ${r.unit}/worker-hour)` }))]} />
                  <Choice label={`Trade ${i + 1} task ${k + 1} location`} disabled={disabled} value={task.location} onChange={(v) => setTask(i, k, { location: v })} style={{ flex: "1 1 150px" }}
                    options={[{ value: "", label: "Location..." }, ...codes.map((c) => ({ value: c.code, label: c.label }))]} />
                  <Input label={`Trade ${i + 1} task ${k + 1} quantity`} disabled={disabled} value={task.quantity} placeholder={`Quantity${rates[task.rate_code] ? ` (${rates[task.rate_code].unit})` : ""}`}
                    onChange={(v) => setTask(i, k, { quantity: v })} style={{ flex: "0 1 120px" }} />
                  {scope.advanced && Object.entries(reference.modifiers).map(([key, opts]) => (
                    <Choice key={key} label={`${key} modifier`} disabled={disabled} value={String((task.modifiers || {})[key] || 100)} style={{ flex: "1 1 150px" }}
                      onChange={(v) => setTask(i, k, { modifiers: { ...(task.modifiers || {}), [key]: Number(v) } })}
                      options={opts.map(([label, pct]) => ({ value: String(pct), label: `${label}${pct !== 100 ? ` (${pct}%)` : ""}` }))} />
                  ))}
                  {!disabled && <button type="button" aria-label="Remove task" onClick={() => setTrade(i, { tasks: tr.tasks.filter((_, j) => j !== k) })} style={{ border: "none", background: "none", color: t.textMuted, cursor: "pointer" }}><Trash2 size={14} /></button>}
                </div>
              ))}
              {!disabled && (
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <Button icon={Plus} onClick={() => setTrade(i, { tasks: [...tr.tasks, { rate_code: "", location: codes[0]?.code || "", quantity: "", modifiers: {} }] })}>Add a task</Button>
                  <Button icon={Trash2} onClick={() => setScope({ ...scope, trades: scope.trades.filter((_, j) => j !== i) })}>Remove trade</Button>
                </div>
              )}
            </div>
          );
        })}
        {!disabled && <Button icon={Plus} onClick={() => setScope({ ...scope, trades: [...scope.trades, { trade: reference.trades[0].trade, mobilisation_id: p.mobilisations[0]?.id || "", crew_size: "3", classification: "Tradesperson", tasks: [] }] })}>Add a trade</Button>}
        {!scope.advanced && <p style={{ fontSize: 12, color: t.textMuted, marginBottom: 0 }}>Advanced mode adds production modifiers: access, programme complexity, crew mix and materials handling.</p>}
      </Card>

      <Card title="Non-production roles" hint="Supervision and support are added or waived explicitly - never just forgotten.">
        <label style={{ fontSize: 13, display: "flex", gap: 6, alignItems: "center" }}>
          <Input type="checkbox" label="Waive non-production roles" disabled={disabled} checked={Boolean(np.waived)} onChange={(v) => setScope({ ...scope, non_production: { ...np, waived: v } })} />
          Waive: this request carries no supervision or support
        </label>
        {!np.waived && np.roles.map((r, i) => (
          <div key={i} style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <Choice label={`Role ${i + 1}`} disabled={disabled} value={r.role} style={{ maxWidth: 200 }} options={reference.non_production_roles}
              onChange={(v) => setScope({ ...scope, non_production: { ...np, roles: np.roles.map((x, j) => (j === i ? { ...x, role: v } : x)) } })} />
            <Input label={`Role ${i + 1} count`} disabled={disabled} value={r.count} placeholder="Count" style={{ maxWidth: 90 }}
              onChange={(v) => setScope({ ...scope, non_production: { ...np, roles: np.roles.map((x, j) => (j === i ? { ...x, count: v.replace(/\D/g, "") } : x)) } })} />
            <Input label={`Role ${i + 1} weeks`} disabled={disabled} value={r.weeks} placeholder="Weeks" style={{ maxWidth: 90 }}
              onChange={(v) => setScope({ ...scope, non_production: { ...np, roles: np.roles.map((x, j) => (j === i ? { ...x, weeks: v.replace(/\D/g, "") } : x)) } })} />
            {!disabled && <Button icon={Trash2} onClick={() => setScope({ ...scope, non_production: { ...np, roles: np.roles.filter((_, j) => j !== i) } })}>Remove</Button>}
          </div>
        ))}
        {!np.waived && !disabled && <div style={{ marginTop: 8 }}><Button icon={Plus} onClick={() => setScope({ ...scope, non_production: { ...np, roles: [...np.roles, { role: "Supervisor", count: "1", weeks: "4" }] } })}>Add a role</Button></div>}
      </Card>
    </div>
  );
}

function Financials({ scope, setScope, disabled }) {
  const f = scope.financials;
  const setF = (k, rows) => setScope({ ...scope, financials: { ...f, [k]: rows } });
  return (
    <Grid cols={2} min={320}>
      <Card title="Materials" hint="Optional. Consumables and materials the trades supply.">
        {f.materials.map((m, i) => (
          <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6 }}>
            <Input label={`Material ${i + 1}`} disabled={disabled} value={m.description} onChange={(v) => setF("materials", f.materials.map((x, j) => (j === i ? { ...x, description: v } : x)))} />
            <Input label={`Material ${i + 1} amount`} disabled={disabled} value={m.amount} placeholder="$" style={{ maxWidth: 120 }} onChange={(v) => setF("materials", f.materials.map((x, j) => (j === i ? { ...x, amount: v } : x)))} />
          </div>
        ))}
        {!disabled && <Button icon={Plus} onClick={() => setF("materials", [...f.materials, { description: "", amount: "" }])}>Add materials</Button>}
      </Card>
      <Card title="Plant" hint="Optional. Hired by the week.">
        {f.plant.map((m, i) => (
          <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6 }}>
            <Input label={`Plant ${i + 1}`} disabled={disabled} value={m.description} onChange={(v) => setF("plant", f.plant.map((x, j) => (j === i ? { ...x, description: v } : x)))} />
            <Input label={`Plant ${i + 1} weeks`} disabled={disabled} value={m.weeks} placeholder="Weeks" style={{ maxWidth: 80 }} onChange={(v) => setF("plant", f.plant.map((x, j) => (j === i ? { ...x, weeks: v } : x)))} />
            <Input label={`Plant ${i + 1} rate`} disabled={disabled} value={m.rate_per_week} placeholder="$/week" style={{ maxWidth: 100 }} onChange={(v) => setF("plant", f.plant.map((x, j) => (j === i ? { ...x, rate_per_week: v } : x)))} />
          </div>
        ))}
        {!disabled && <Button icon={Plus} onClick={() => setF("plant", [...f.plant, { description: "", weeks: "", rate_per_week: "" }])}>Add plant</Button>}
      </Card>
    </Grid>
  );
}

function ResultView({ result, compact }) {
  const { t } = useTheme();
  if (!result) return null;
  const dates = result.trades.filter((x) => x.start_date && x.finish_date && x.work_days > 0);
  const lo = dates.length ? Math.min(...dates.map((x) => Date.parse(x.start_date))) : 0;
  const hi = dates.length ? Math.max(...dates.map((x) => Date.parse(x.finish_date)), result.target_finish ? Date.parse(result.target_finish) : 0) : 1;
  const pos = (d) => `${((Date.parse(d) - lo) / Math.max(hi - lo, 1)) * 100}%`;
  return (
    <>
      <Grid cols={compact ? 2 : 4} min={150}>
        <Stat label="Total budget" value={cents(result.total_cents)} emphasis />
        <Stat label="Labour hours" value={hours(result.total_hours_x100)} sub={`${cents(result.labour_cents)} labour`} />
        <Stat label="Peak crew" value={fmtInt(result.peak_crew)} />
        <Stat label="Finish" value={result.finish_date ? fmtDate(result.finish_date) : "-"} tone={result.finish_date && result.target_finish ? (result.on_time ? "good" : "critical") : undefined}
          sub={result.target_finish ? `Target ${fmtDate(result.target_finish)}` : undefined} />
      </Grid>
      <SectionTitle>By trade</SectionTitle>
      <Table rows={result.trades} columns={[
        { key: "trade", label: "Trade" }, { key: "mobilisation", label: "Mobilisation" }, { key: "crew_size", label: "Crew", align: "right" },
        { key: "hours", label: "Hours", align: "right", render: (r) => hours(r.hours_x100) },
        { key: "ot", label: "Of which overtime", align: "right", render: (r) => hours(r.overtime_hours_x100) },
        { key: "work_days", label: "Working days", align: "right" },
        { key: "start", label: "Start", render: (r) => fmtDate(r.start_date) }, { key: "finish", label: "Finish", render: (r) => fmtDate(r.finish_date) },
        { key: "on_time", label: "Against target", render: (r) => (r.work_days === 0 ? "-" : r.on_time ? <Badge tone="good">On time</Badge> : <Badge tone="critical">Late</Badge>) },
        { key: "labour", label: "Labour", align: "right", render: (r) => cents(r.labour_cents) },
      ]} />
      {dates.length > 0 && (
        <Card title="Timeline" hint="Each trade from its mobilisation start, by working days. No dependencies between trades: this is a feasibility check, not a programme." style={{ marginTop: 14 }}>
          {dates.map((x) => (
            <div key={x.trade} style={{ display: "grid", gridTemplateColumns: "130px 1fr", gap: 8, alignItems: "center", marginBottom: 6, fontSize: 12 }}>
              <span>{x.trade}</span>
              <div style={{ position: "relative", height: 16, background: t.code, borderRadius: 4 }}>
                <div style={{ position: "absolute", left: pos(x.start_date), right: `calc(100% - ${pos(x.finish_date)})`, top: 2, bottom: 2, borderRadius: 3, background: x.on_time ? t.series[0] : t.status.critical }}
                  title={`${fmtDate(x.start_date)} to ${fmtDate(x.finish_date)}`} />
                {result.target_finish && <div style={{ position: "absolute", left: pos(result.target_finish), top: -3, bottom: -3, width: 2, background: t.text }} title="Target finish" />}
              </div>
            </div>
          ))}
          <p style={{ fontSize: 11.5, color: t.textMuted, margin: "6px 0 0" }}>The black line is the target finish. A red bar finishes after it.</p>
        </Card>
      )}
      {!compact && result.tasks.length > 0 && (
        <>
          <SectionTitle>Cost codes</SectionTitle>
          <Table rows={result.tasks} maxHeight={320} columns={[
            { key: "cost_code", label: "Cost code" }, { key: "task", label: "Task" },
            { key: "qty", label: "Quantity", align: "right", render: (r) => `${(r.quantity_x100 / 100).toLocaleString("en-AU")} ${r.unit}` },
            { key: "mod", label: "Modifier", align: "right", render: (r) => `${(r.modifier_x10000 / 100).toFixed(0)}%` },
            { key: "hours", label: "Hours", align: "right", render: (r) => hours(r.hours_x100) },
          ]} />
        </>
      )}
    </>
  );
}

function Wizard({ reference, rates, opened, onSaved }) {
  const { t } = useTheme();
  const toast = useToast();
  const { data: mine, reload } = useApi("/api/trades/requests");
  const [scope, setScope] = useState(null);
  const [requestId, setRequestId] = useState(null);
  const [title, setTitle] = useState("");
  const [phase, setPhase] = useState("scope");
  const [error, setError] = useState(null);
  const [savedAt, setSavedAt] = useState(null);
  const [server, setServer] = useState(null);
  const [recovery, setRecovery] = useState(() => readLocal(LOCAL));
  const [revisionOf, setRevisionOf] = useState("");
  const writable = canWrite();

  useEffect(() => { if (opened) open(opened); }, [opened]); // eslint-disable-line react-hooks/exhaustive-deps

  // The browser keeps an unsaved copy as you type, so a closed tab loses nothing.
  useEffect(() => {
    if (!scope) return;
    writeLocal(LOCAL, { scope, title, requestId, at: new Date().toISOString() });
    setSavedAt(new Date().toISOString());
  }, [scope, title]); // eslint-disable-line react-hooks/exhaustive-deps

  const preview = useMemo(() => (scope ? calculate(scope, rates, reference) : null), [scope, rates, reference]);
  const gaps = useMemo(() => (scope ? missing(scope, rates) : []), [scope, rates]);

  function open(req) {
    setScope(req.scope);
    setRequestId(req.status === "draft" ? req.request_id : null);
    setTitle(req.title);
    setServer(req.result);
    setPhase("scope");
    setRecovery(null);
  }

  const save = async (submit) => {
    setError(null);
    try {
      const res = await apiWrite("/api/trades/requests", { request_id: requestId, title, scope, submit });
      setServer(res.result);
      if (submit) {
        toast(`${res.request_id} submitted for approval. It is now Pending.`, { tone: "good" });
        writeLocal(LOCAL, null);
        setScope(null);
        setRequestId(null);
        onSaved(res);
      } else {
        setRequestId(res.request_id);
        toast(`Draft ${res.request_id} saved. The stored figures are the server's.`, { tone: "good" });
      }
      reload();
    } catch (e) { setError(e); }
  };

  const loadRevision = async () => {
    try { open(await apiWrite(`/api/trades/requests/${revisionOf}/revise`)); reload(); } catch (e) { setError(e); }
  };

  if (!scope) {
    const drafts = (mine || []).filter((r) => r.status === "draft" && r.author === actorName());
    const submitted = (mine || []).filter((r) => r.status !== "draft");
    return (
      <>
        <ReadOnlyNotice what="creating or submitting a request" role="Site supervisor" />
        <ErrorNote error={error} />
        {recovery && (
          <Callout tone="warning" title="Unsaved request found in this browser">
            Kept {fmtDateTime(recovery.at, { seconds: false })}{recovery.title ? `: ${recovery.title}` : ""}.
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <Button onClick={() => { setScope(recovery.scope); setTitle(recovery.title); setRequestId(recovery.requestId); setRecovery(null); }}>Resume</Button>
              <Button onClick={() => { writeLocal(LOCAL, null); setRecovery(null); }}>Discard</Button>
            </div>
          </Callout>
        )}
        <Grid cols={3} min={260}>
          <Card title="New request" hint="Start from an empty scope.">
            <CTAButton icon={FilePlus2} onClick={() => { setScope(blankScope(reference.today)); setTitle(""); setRequestId(null); setServer(null); setPhase("scope"); }}>New request</CTAButton>
          </Card>
          <Card title="Resume a draft" hint="Drafts are private to their author.">
            {drafts.length === 0 ? <p style={{ fontSize: 13, color: t.textMuted }}>You have no drafts.</p> : drafts.map((d) => (
              <div key={d.request_id} style={{ marginBottom: 6 }}><Button icon={History} onClick={async () => open(await api(`/api/trades/requests/${d.request_id}`))}>{d.request_id} {d.title}</Button></div>
            ))}
          </Card>
          <Card title="Load a revision" hint="A new version of a submitted request, or a base for a new one. The original is kept.">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Choice label="Request to revise" value={revisionOf} onChange={setRevisionOf} style={{ flex: 1, minWidth: 160 }}
                options={[{ value: "", label: "Choose a request..." }, ...submitted.map((r) => ({ value: r.request_id, label: `${r.request_id} v${r.version} ${r.title} (${r.status})` }))]} />
              <Button icon={GitBranch} disabled={!revisionOf || !writable} onClick={loadRevision}>Load</Button>
            </div>
          </Card>
        </Grid>
      </>
    );
  }

  const phases = [["scope", "1. Scope"], ["financials", "2. Financials"], ["review", "3. Review & submit"]];
  const idx = phases.findIndex((x) => x[0] === phase);
  const scopeDone = gaps.length === 0;
  return (
    <div>
      <ReadOnlyNotice what="saving or submitting" role="Site supervisor" />
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        {phases.map(([key, label], i) => (
          <button key={key} type="button" onClick={() => (i === 0 || scopeDone) && setPhase(key)} style={{
            border: "none", borderRadius: 999, padding: "6px 14px", fontFamily: "inherit", fontSize: 12.5, fontWeight: 700,
            background: phase === key ? t.ctaBg : i < idx ? t.accentGlow : t.code, color: phase === key ? t.ctaText : i > 0 && !scopeDone ? t.textDim : t.text,
            cursor: i === 0 || scopeDone ? "pointer" : "not-allowed",
          }}>{i < idx ? <CheckCircle2 size={12} style={{ verticalAlign: -2, marginRight: 4 }} /> : null}{label}</button>
        ))}
        <div style={{ flex: 1 }} />
        <Field label="Request title" width={300}><Input label="Request title" value={title} onChange={setTitle} placeholder="e.g. Structure - base request" disabled={!writable} /></Field>
      </div>
      <ErrorNote error={error} />
      {phase === "scope" && <ScopeEditor scope={scope} setScope={setScope} reference={reference} rates={rates} disabled={!writable} />}
      {phase === "financials" && <Financials scope={scope} setScope={setScope} disabled={!writable} />}
      {phase === "review" && (
        <>
          <Callout tone={preview.on_time ? "good" : "warning"} title={preview.on_time ? "Finishes inside the target" : "Finishes after the target"}>
            Calculated finish {fmtDate(preview.finish_date)} against a target of {fmtDate(preview.target_finish)}, counting working days only -
            weekends{scope.project.work_saturdays ? " (Saturdays worked)" : ""} and Queensland public holidays skipped.
          </Callout>
          <ResultView result={preview} />
          {server && (
            <p style={{ fontSize: 12, color: t.textMuted }}>
              Server's figures at the last save: {cents(server.total_cents)} and {hours(server.total_hours_x100)} hours
              {server.total_cents === preview.total_cents && server.total_hours_x100 === preview.total_hours_x100 ? " - the same as the preview." : " - save again to bring them up to date."}
            </p>
          )}
        </>
      )}

      {/* Sticky action bar */}
      <div style={{
        position: "sticky", bottom: -110, marginTop: 16, background: t.surface, border: `1px solid ${t.border}`, borderRadius: 12, padding: "10px 14px",
        display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", boxShadow: "0 -4px 16px rgba(0,0,0,0.06)", zIndex: 4,
      }}>
        <span style={{ fontSize: 12, color: t.textMuted }}>{savedAt ? `Kept in this browser ${fmtDateTime(savedAt, { seconds: false }).slice(11)}` : ""}{requestId ? ` - draft ${requestId}` : ""}</span>
        <span style={{ fontSize: 12.5, fontWeight: 650 }}>{cents(preview.total_cents)} - {hours(preview.total_hours_x100)} h - finish {fmtDate(preview.finish_date)}</span>
        <div style={{ flex: 1 }} />
        {phase === "scope" && !scopeDone && <span style={{ fontSize: 12, color: t.status.warning, fontWeight: 650 }}>Complete first: {gaps.join(", ")}</span>}
        <Button icon={ArrowLeft} disabled={idx === 0} onClick={() => setPhase(phases[idx - 1][0])}>Back</Button>
        <Button icon={Save} disabled={!writable || !scope.project.project_id} onClick={() => save(false)}>Save draft</Button>
        {phase !== "review"
          ? <CTAButton icon={ArrowRight} disabled={!scopeDone} onClick={() => setPhase(phases[idx + 1][0])}>Continue</CTAButton>
          : <CTAButton icon={Send} disabled={!writable || !scopeDone} onClick={() => save(true)}>Submit for approval</CTAButton>}
        <Button icon={Trash2} onClick={() => { if (window.confirm("Close this request? An unsaved copy stays in this browser.")) setScope(null); }}>Close</Button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------- library --
function Library({ reference, rates, onChanged }) {
  const { t } = useTheme();
  const toast = useToast();
  const { data: cases } = useApi("/api/trades/parity");
  const [edit, setEdit] = useState(null);
  const [error, setError] = useState(null);
  const parity = useMemo(() => {
    if (!cases) return null;
    return cases.map((c) => {
      const mine = calculate(c.scope, Object.fromEntries(Object.entries(rates).map(([k, v]) => [k, v])), reference);
      const diff = PARITY_FIELDS.filter((f) => String(mine[f]) !== String(c.expected[f]));
      return { name: c.name, ok: diff.length === 0, diff, total: c.expected.total_cents };
    });
  }, [cases, rates, reference]);
  const saveRate = async () => {
    setError(null);
    try {
      await apiWrite(`/api/trades/library/${edit.rate_code}`, { rate: edit.rate, reason: edit.reason }, "PUT");
      toast(`${edit.rate_code} updated. Every new calculation uses it from now on.`, { tone: "good" });
      setEdit(null);
      onChanged();
    } catch (e) { setError(e); }
  };
  const agree = parity ? parity.filter((p) => p.ok).length : 0;
  return (
    <>
      <Grid cols={2} min={300}>
        <Card title="Browser and server agree" hint="The wizard calculates in the browser on every keystroke; the stored numbers come from the server. Both engines run over the same scopes here - the eight stored requests and three awkward ones - and must agree to the cent and the day.">
          {!parity ? <Loading /> : (
            <>
              <div style={{ fontSize: 22, fontWeight: 750, color: agree === parity.length ? t.status.good : t.status.critical }}>{agree} of {parity.length} agree</div>
              <Table rows={parity} maxHeight={240} columns={[{ key: "name", label: "Case", wrap: true },
                { key: "total", label: "Budget", align: "right", render: (r) => cents(r.total) },
                { key: "ok", label: "", render: (r) => (r.ok ? <Badge tone="good">Same</Badge> : <Badge tone="critical">Differs: {r.diff.join(", ")}</Badge>) }]} />
            </>
          )}
        </Card>
        <Card title="One library, every task" hint="A change applies to new calculations; submitted requests keep the numbers they were decided on. Every change needs a reason and is in the audit log.">
          <KeyValues items={[["Rates", reference.library.length], ["Trades", reference.trades.length],
            ["Loaded labour rates", Object.entries(reference.labour_rates).map(([k, v]) => `${k} ${fmtAud(v / 100)}/h`).join(", ")]]} />
          <p style={{ fontSize: 11.5, color: t.textMuted }}>Labour rates are assumptions made for the demo, not anyone's actual costs.</p>
        </Card>
      </Grid>
      <SectionTitle>Production rates</SectionTitle>
      <ErrorNote error={error} />
      <Card pad={0} rule={false}>
        <Table rows={reference.library} maxHeight={640} columns={[
          { key: "rate_code", label: "Code" }, { key: "trade", label: "Trade" }, { key: "task", label: "Task", wrap: true },
          { key: "rate", label: "Units per worker-hour", align: "right", render: (r) => (edit?.rate_code === r.rate_code ? (
            <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
              <Input label="New rate" value={edit.rate} onChange={(v) => setEdit({ ...edit, rate: v })} style={{ width: 80 }} />
              <Input label="Reason" value={edit.reason} placeholder="Reason" onChange={(v) => setEdit({ ...edit, reason: v })} style={{ width: 200 }} />
              <Button onClick={saveRate}>Save</Button><Button onClick={() => setEdit(null)}>Cancel</Button>
            </div>
          ) : `${r.rate} ${r.unit}`) },
          { key: "default_crew", label: "Typical crew", align: "right" },
          { key: "updated", label: "Last changed", render: (r) => `${fmtDate(r.updated_at)} by ${r.updated_by}` },
          { key: "edit", label: "", render: (r) => canWrite() && edit?.rate_code !== r.rate_code && <Button onClick={() => setEdit({ rate_code: r.rate_code, rate: String(r.rate), reason: "" })}>Change</Button> },
        ]} />
      </Card>
    </>
  );
}

// ------------------------------------------------------------------ tracking --
function Review({ id, onClose, onDecided, onRevise }) {
  const { t } = useTheme();
  const toast = useToast();
  const { data, reload } = useApi(id ? `/api/trades/requests/${id}` : null);
  const [decision, setDecision] = useState("accepted");
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState(null);
  useEffect(() => { setError(null); setFeedback(""); }, [id]);
  const decide = async () => {
    setError(null);
    try {
      await apiWrite(`/api/trades/requests/${id}/review`, { decision, feedback });
      toast(`${id} ${decision}.`, { tone: "good" });
      reload();
      onDecided();
    } catch (e) { setError(e); }
  };
  return (
    <Drawer open={Boolean(id)} onClose={onClose} width={760} title={data ? `${data.request_id} - ${data.title}` : ""}
      subtitle={data ? `${data.project_id} ${data.project_name}. Version ${data.version}, by ${data.author}.` : ""}>
      {data && (
        <>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
            <Badge tone={STATUS_TONE[data.status]}>{data.status}</Badge>
            {data.reviewer && <span style={{ fontSize: 12.5, color: t.textMuted }}>Decided by {data.reviewer} on {fmtDate(data.reviewed_at)}: "{data.feedback}"</span>}
          </div>
          <ResultView result={data.result} compact />
          {data.versions.length > 1 && (
            <>
              <SectionTitle>Versions</SectionTitle>
              <Table rows={data.versions} columns={[{ key: "version", label: "v" }, { key: "request_id", label: "Request" },
                { key: "status", label: "Status", render: (r) => <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge> },
                { key: "total", label: "Budget", align: "right", render: (r) => fmtAud(r.total) }, { key: "feedback", label: "Feedback", wrap: true }]} />
            </>
          )}
          {["pending", "tentative"].includes(data.status) && (
            <Card title="Decision" style={{ marginTop: 14 }} hint="Feedback is required for any decision, and nobody decides their own request - both are enforced by the server, not this form.">
              <ErrorNote error={error} />
              <SegmentedControl label="Decision" value={decision} onChange={setDecision}
                options={[{ value: "accepted", label: "Accept" }, { value: "tentative", label: "Tentative" }, { value: "rejected", label: "Reject" }]} />
              <textarea aria-label="Feedback" value={feedback} onChange={(e) => setFeedback(e.target.value)} rows={3} placeholder="Feedback for the author (required)"
                style={{ width: "100%", marginTop: 10, borderRadius: 8, border: `1px solid ${t.border}`, padding: 8, fontFamily: "inherit", fontSize: 13, background: t.surface, color: t.text }} />
              <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <CTAButton onClick={decide} disabled={!canWrite()}>Record the decision as {actorName()}</CTAButton>
                {data.author === actorName() && <span style={{ fontSize: 12, color: t.status.warning }}>You are the author - this will be refused.</span>}
              </div>
            </Card>
          )}
          {data.status !== "draft" && canWrite() && <div style={{ marginTop: 12 }}><Button icon={GitBranch} onClick={() => onRevise(data.request_id)}>Load as a revision</Button></div>}
        </>
      )}
    </Drawer>
  );
}

function Tracking({ reloadKey, onRevise }) {
  const { t } = useTheme();
  const { data, reload } = useApi("/api/trades/requests");
  const { data: jobs, reload: reloadJobs } = useApi("/api/trades/jobs");
  const [params, setParams] = useSearchParams();
  const open = params.get("request");
  const setOpen = (id) => setParams((p) => { if (id) p.set("request", id); else p.delete("request"); return p; }, { replace: true });
  useEffect(() => { reload(); reloadJobs(); }, [reloadKey, reload, reloadJobs]);
  if (!data || !jobs) return <Loading />;
  const waiting = data.filter((r) => ["pending", "tentative"].includes(r.status)).length;
  return (
    <>
      <Grid cols={3} min={200}>
        <Stat label="Awaiting a decision" value={waiting} emphasis />
        <Stat label="Accepted requests" value={data.filter((r) => r.status === "accepted").length} />
        <Stat label="Approved labour budget" value={fmtAud(jobs.reduce((s, j) => s + j.budget, 0), { short: true })} sub="Across every job" />
      </Grid>
      <SectionTitle>Requests</SectionTitle>
      <Card pad={0} rule={false}>
        <Table rows={data} maxHeight={520} onRowClick={(r) => setOpen(r.request_id)} columns={[
          { key: "request_id", label: "Request", render: (r) => <b>{r.request_id}</b> }, { key: "version", label: "v", align: "right" },
          { key: "project_id", label: "Job" }, { key: "title", label: "Title", wrap: true },
          { key: "status", label: "Status", render: (r) => <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge> },
          { key: "author", label: "Author" },
          { key: "total", label: "Budget", align: "right", render: (r) => cents(r.total_cents) },
          { key: "finish", label: "Finish", render: (r) => <span style={{ color: r.on_time ? t.text : t.status.critical }}>{fmtDate(r.finish_date)}</span> },
          { key: "target", label: "Target", render: (r) => fmtDate(r.target_finish) },
        ]} />
      </Card>
      <SectionTitle>By job: base plus top-ups</SectionTitle>
      <Card pad={0} rule={false}>
        <Table rows={jobs} columns={[
          { key: "project_id", label: "Job" }, { key: "project_name", label: "Name", wrap: true }, { key: "requests", label: "Accepted requests" },
          { key: "hours", label: "Hours", align: "right", render: (r) => Number(r.hours).toLocaleString("en-AU", { maximumFractionDigits: 0 }) },
          { key: "budget", label: "Labour budget", align: "right", render: (r) => fmtAud(r.budget) },
          { key: "awaiting_review", label: "Awaiting", align: "right" },
        ]} />
      </Card>
      <p style={{ fontSize: 12, color: t.textMuted }}>Only accepted requests count. A tentative one stays with its reviewer.</p>
      <Review id={open} onClose={() => setOpen(null)} onDecided={() => { reload(); reloadJobs(); }} onRevise={(id) => { setOpen(null); onRevise(id); }} />
    </>
  );
}

// ---------------------------------------------------------------------- page --
export default function TradePlanner() {
  const { data: reference, error, reload } = useApi("/api/trades/reference");
  const rates = useRates(reference);
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "tracking";
  const setTab = (key) => setParams((p) => { p.set("tab", key); p.delete("request"); return p; }, { replace: true });
  const [reloadKey, setReloadKey] = useState(0);
  const [opened, setOpened] = useState(null);
  if (error) return <ErrorNote error={error} />;
  if (!reference) return <><PageHeader title="Trade Planner" /><Loading /></>;
  const revise = async (id) => {
    const req = await apiWrite(`/api/trades/requests/${id}/revise`);
    setOpened(req);
    setTab("create");
  };
  return (
    <>
      <PageHeader
        title="Trade Planner"
        brief="Sit with estimators and site managers, spot what slows them down, and automate it"
        subtitle="A labour budget and feasibility check, ported from a spreadsheet model into a guided wizard: tasks draw production rates from one shared library, locations generate the cost codes, and a second person accepts or rejects with feedback. Working-day arithmetic per trade; no task dependencies."
      />
      <MountedTabs value={tab} onChange={setTab} right={<Button icon={RotateCcw} onClick={() => { reload(); setReloadKey((k) => k + 1); }}>Refresh</Button>} tabs={[
        { key: "create", label: "Create / Edit", render: () => <Wizard reference={reference} rates={rates} opened={opened} onSaved={() => { setReloadKey((k) => k + 1); setTab("tracking"); }} /> },
        { key: "library", label: "Library", render: () => <Library reference={reference} rates={rates} onChanged={reload} /> },
        { key: "tracking", label: "Tracking", render: () => <Tracking reloadKey={reloadKey} onRevise={revise} /> },
        { key: "audit", label: "Audit", render: () => <AuditTable path="/api/trades/audit" reloadKey={reloadKey} project /> },
      ]} />
      <Callout tone="neutral" title="Not built yet">
        Budget against actuals: it needs the project management feed of time cards and achieved quantities, planned for a second phase.
        Task dependencies: deliberately out - a critical-path programme belongs in the scheduling tool.
      </Callout>
    </>
  );
}
