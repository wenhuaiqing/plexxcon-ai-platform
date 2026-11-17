// Material Supply Register: concrete and reinforcement for a job, from the
// contract budget through delivery dockets to docket-level invoice
// reconciliation. Two levels: the portfolio, then one job's workspace.

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart } from "recharts";
import { ArrowLeft, CircleHelp, FileText, Inbox, Plus, Ruler, Search, Trash2, Undo2, Upload } from "lucide-react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { api, apiUpload, apiWrite, fmtAud, fmtDate, fmtQty, useApi } from "../../lib/api.js";
import { Choice, Field, FormGrid, Input, Modal, MountedTabs, ReadOnlyNotice, canWrite, useToast } from "../../lib/kit.jsx";
import {
  Badge, Button, CTAButton, Callout, Card, ChartFrame, ChartOrTable, ErrorNote, Grid, Loading, PageHeader, SectionTitle, SegmentedControl, Stat,
  Table, useChartParts,
} from "../../lib/ui.jsx";

const RECON = { green: ["Balanced", "good"], amber: ["Check", "warning"], red: ["Over 5% out", "critical"] };
const MATCH = {
  matched: ["Matched to docket", "good"], surcharge: ["Listed surcharge", "good"], duplicate: ["Docket already billed", "critical"],
  unmatched: ["Docket not on register", "critical"], unpriced: ["No rate on that date", "warning"], unlisted: ["Charge not on price list", "warning"],
};
const TABS = [["dashboard", "Dashboard"], ["tracking", "Tracking"], ["prices", "Price List"], ["deliveries", "Delivery Log"], ["invoices", "Invoices"], ["audit", "Audit Log"]];

function ReconBadge({ status }) {
  const [label, tone] = RECON[status] || [status, "neutral"];
  return <Badge tone={tone}>{status === "green" ? "Green" : status === "amber" ? "Amber" : "Red"} - {label}</Badge>;
}

// ------------------------------------------------------------- walkthrough --
function Walkthrough({ open, onClose, steps, current, onGo }) {
  const { t } = useTheme();
  const start = Math.max(steps.findIndex((s) => s.tab === current), 0);
  const [i, setI] = useState(start);
  useEffect(() => { if (open) setI(start); }, [open, start]);
  const s = steps[i];
  return (
    <Modal open={open} onClose={onClose} title={`Step ${i + 1} of ${steps.length}: ${s?.title || ""}`} width={520} footer={<>
      <Button disabled={i === 0} onClick={() => setI(i - 1)}>Back</Button>
      {s?.tab !== current && <Button onClick={() => { onGo(s.tab); onClose(); }}>Go there</Button>}
      {i < steps.length - 1 ? <CTAButton onClick={() => setI(i + 1)}>Next</CTAButton> : <CTAButton onClick={onClose}>Done</CTAButton>}
    </>}>
      <p style={{ fontSize: 14, lineHeight: 1.6, marginTop: 0 }}>{s?.text}</p>
      <div style={{ display: "flex", gap: 5 }}>
        {steps.map((x, k) => <span key={k} style={{ flex: 1, height: 4, borderRadius: 2, background: k <= i ? t.brand : t.code }} />)}
      </div>
      <p style={{ fontSize: 12, color: t.textMuted }}>The ? button opens this at the step for the screen you are on.</p>
    </Modal>
  );
}

// --------------------------------------------------------------- portfolio --
function Portfolio({ onOpen }) {
  const { t } = useTheme();
  const toast = useToast();
  const { data, error, reload } = useApi("/api/msr/portfolio");
  const [q, setQ] = useState("");
  const [found, setFound] = useState(null);
  const [err, setErr] = useState(null);
  const [help, setHelp] = useState(false);
  const search = async () => setFound(await api(`/api/msr/jobs?q=${encodeURIComponent(q)}`));
  const enrol = async (id) => {
    setErr(null);
    try { await apiWrite("/api/msr/enrol", { project_id: id }); toast(`Job ${id} enrolled.`, { tone: "good" }); reload(); onOpen(id); } catch (e) { setErr(e); }
  };
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const section = (reg) => {
    const meta = data.registers[reg];
    return (
      <>
        <SectionTitle>{meta.label} <span style={{ fontWeight: 500, color: t.textMuted, fontSize: 12 }}>(quantities in {meta.unit === "m3" ? "m³" : "tonnes"})</span></SectionTitle>
        <Card pad={0} rule={false}>
          <Table rows={data.summary[reg]} onRowClick={(r) => onOpen(r.project_id, reg)} columns={[
            { key: "project_id", label: "Job", render: (r) => <b>{r.project_id}</b> }, { key: "name", label: "Project", wrap: true },
            { key: "budget_amount", label: "Budget", align: "right", render: (r) => fmtAud(r.budget_amount) },
            { key: "fac_amount", label: "Forecast at completion", align: "right", render: (r) => fmtAud(r.fac_amount) },
            { key: "qty", label: "Delivered / forecast", align: "right", render: (r) => `${fmtQty(r.delivered_qty, meta.unit, 1)} of ${fmtQty(r.fac_qty, meta.unit, 1)}` },
            { key: "invoiced_amount", label: "Invoiced", align: "right", render: (r) => fmtAud(r.invoiced_amount) },
            { key: "recon", label: "Invoices", render: (r) => (
              <span style={{ display: "inline-flex", gap: 4, flexWrap: "wrap" }}>
                {r.green > 0 && <Badge tone="good">{r.green} green</Badge>}{r.amber > 0 && <Badge tone="warning">{r.amber} amber</Badge>}{r.red > 0 && <Badge tone="critical">{r.red} red</Badge>}
              </span>
            ) },
            { key: "inbox", label: "Inbox", align: "right", render: (r) => (r.inbox ? <Badge tone="ai">{r.inbox} to review</Badge> : "-") },
          ]} />
        </Card>
      </>
    );
  };
  return (
    <>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginBottom: -6 }}><Button icon={CircleHelp} onClick={() => setHelp(true)}>How it works</Button></div>
      {section("concrete")}
      {section("reo")}
      <SectionTitle>Add project</SectionTitle>
      <Card hint="A job has no register until it is enrolled; access to a register follows the job.">
        <ErrorNote error={err} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Input label="Job number or name" value={q} onChange={setQ} placeholder="Job number, e.g. 2444" style={{ maxWidth: 260 }} onKeyDown={(e) => e.key === "Enter" && search()} />
          <Button icon={Search} onClick={search}>Search</Button>
        </div>
        {found && (
          <div style={{ marginTop: 10 }}>
            <Table rows={found} empty="No job matches." columns={[{ key: "project_id", label: "Job" }, { key: "name", label: "Project", wrap: true },
              { key: "status", label: "Status" },
              { key: "go", label: "", render: (r) => (r.enrolled ? <Button onClick={() => onOpen(r.project_id)}>Open</Button>
                : <CTAButton disabled={!canWrite()} onClick={() => enrol(r.project_id)}>Enrol</CTAButton>) }]} />
          </div>
        )}
      </Card>
      <Walkthrough open={help} onClose={() => setHelp(false)} steps={data.walkthrough} current="portfolio" onGo={() => {}} />
    </>
  );
}

// ------------------------------------------------------------ measure tool --
// A lightweight take-off: trace an area or a length on the drawing and turn it
// into a quantity. The drawing is a synthetic sheet at 1:200 (10 px = 1 m).
function MeasureTool({ open, onClose, register, line, onUse }) {
  const { t } = useTheme();
  const [mode, setMode] = useState("area");
  const [pts, setPts] = useState([]);
  const [factor, setFactor] = useState(register === "concrete" ? "200" : "32");
  useEffect(() => { if (open) { setPts([]); setMode("area"); setFactor(register === "concrete" ? "200" : "32"); } }, [open, register]);
  const PX = 10;
  const click = (e) => {
    const svg = e.currentTarget;
    const r = svg.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * 600;
    const y = ((e.clientY - r.top) / r.height) * 400;
    const snap = (v) => Math.round(v / 5) * 5;
    setPts([...pts, [snap(x), snap(y)]]);
  };
  const area = pts.length > 2 ? Math.abs(pts.reduce((s, [x, y], i) => { const [a, b] = pts[(i + 1) % pts.length]; return s + x * b - a * y; }, 0)) / 2 / (PX * PX) : 0;
  const length = pts.slice(1).reduce((s, p, i) => s + Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]), 0) / PX;
  const f = Number(factor) || 0;
  const qty = register === "concrete" ? (mode === "area" ? area * f / 1000 : length * f / 1000) : (mode === "area" ? area * f / 1000 : length * f / 1000);
  const factorLabel = register === "concrete" ? (mode === "area" ? "Slab thickness (mm)" : "Section area (mm² x 1000 per m)") : (mode === "area" ? "Reinforcement (kg/m²)" : "Reinforcement (kg/m)");
  return (
    <Modal open={open} onClose={onClose} title={`Measure: ${line?.element || ""}`} width={860} footer={<>
      <Button onClick={() => setPts([])}>Clear</Button>
      <CTAButton disabled={qty <= 0} onClick={() => onUse(qty.toFixed(2), `Measured off drawing S-101: ${mode === "area" ? `${area.toFixed(1)} m2` : `${length.toFixed(1)} m`} x ${factor} ${factorLabel.match(/\((.*)\)/)?.[1] || ""}`)}>
        Use {qty.toFixed(2)} {register === "concrete" ? "m³" : "t"} as the forecast
      </CTAButton>
    </>}>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 10 }}>
        <SegmentedControl label="Measure" value={mode} onChange={(v) => { setMode(v); setPts([]); }} options={[{ value: "area", label: "Area" }, { value: "length", label: "Length" }]} />
        <Field label={factorLabel} width={200}><Input label={factorLabel} value={factor} onChange={setFactor} /></Field>
        <span style={{ fontSize: 13 }}>{mode === "area" ? `${area.toFixed(1)} m²` : `${length.toFixed(1)} m`} traced, {pts.length} point(s)</span>
      </div>
      <svg viewBox="0 0 600 400" onClick={click} role="img" aria-label="Drawing S-101, ground floor slab plan" style={{ width: "100%", background: "#FBFBF7", border: `1px solid ${t.border}`, borderRadius: 8, cursor: "crosshair" }}>
        {Array.from({ length: 13 }, (_, i) => <line key={`v${i}`} x1={i * 50} y1={0} x2={i * 50} y2={400} stroke="#E4E6E0" />)}
        {Array.from({ length: 9 }, (_, i) => <line key={`h${i}`} x1={0} y1={i * 50} x2={600} y2={i * 50} stroke="#E4E6E0" />)}
        <path d="M60 60 H420 V160 H540 V340 H60 Z" fill="#EEF3F1" stroke="#33413F" strokeWidth="2.5" />
        <rect x="140" y="120" width="70" height="70" fill="none" stroke="#33413F" strokeDasharray="6 4" />
        <rect x="300" y="230" width="120" height="60" fill="none" stroke="#33413F" strokeDasharray="6 4" />
        {[60, 180, 300, 420, 540].map((x) => [60, 200, 340].map((y) => <rect key={`${x}-${y}`} x={x - 5} y={y - 5} width="10" height="10" fill="#33413F" />))}
        <text x="70" y="385" fontSize="11" fill="#33413F">S-101 GROUND FLOOR SLAB - SCALE 1:200 (grid 5 m) - SYNTHETIC DRAWING</text>
        <text x="200" y="52" fontSize="10" fill="#33413F">36.0 m</text>
        {pts.length > 0 && (mode === "area"
          ? <polygon points={pts.map((p) => p.join(",")).join(" ")} fill="rgba(74,183,195,0.28)" stroke="#1B7F8B" strokeWidth="2" />
          : <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke="#1B7F8B" strokeWidth="3" />)}
        {pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="4" fill="#1B7F8B" />)}
      </svg>
      <p style={{ fontSize: 12, color: t.textMuted }}>Click the corners in order; points snap to 0.5 m. The real tool opens the uploaded drawing PDF; this demo measures a rendered sheet.</p>
    </Modal>
  );
}

// ------------------------------------------------------------ PDF review --
function ReviewDialog({ docId, onClose, onCommitted }) {
  const { t } = useTheme();
  const toast = useToast();
  const [p, setP] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    setP(null); setError(null);
    if (docId) apiWrite(`/api/msr/documents/${docId}/parse`).then(setP).catch(setError);
  }, [docId]);
  const setField = (k) => (v) => setP({ ...p, fields: { ...p.fields, [k]: v } });
  const commit = async () => {
    setError(null);
    try {
      const res = await apiWrite(`/api/msr/documents/${docId}/commit`, {
        kind: p.kind, supplier: p.supplier, parser: p.parser, delivery_id: p.suggested_delivery_id, fields: p.fields, lines: p.lines, rates: p.rates,
      });
      toast(`Confirmed: ${p.kind} recorded as ${res.ref}.`, { tone: "good" });
      onCommitted();
      onClose();
    } catch (e) { setError(e); }
  };
  const job = p?.document?.project_id;
  return (
    <Modal open={Boolean(docId)} onClose={onClose} width={1180} title={p ? `Review ${p.kind}: ${p.document.filename}` : "Reading the document"}
      footer={p && <><Button onClick={onClose}>Cancel - commit nothing</Button><CTAButton disabled={!canWrite()} onClick={commit}>Confirm and record</CTAButton></>}>
      <ErrorNote error={error} />
      {!p ? <Loading label="Reading the PDF" /> : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 14 }}>
          <iframe title="Source PDF" src={`/api/msr/documents/${docId}/source.pdf`} style={{ width: "100%", height: 560, border: `1px solid ${t.border}`, borderRadius: 8, background: "#fff" }} />
          <div>
            <Callout tone={p.parser === "ai_fallback" ? "ai" : p.parser === "none" ? "warning" : "neutral"} title={p.parser === "ai_fallback" ? "Read by the model" : p.parser === "none" ? "Not read" : `Parser: ${p.parser}`}>{p.note}</Callout>
            <ReadOnlyNotice what="confirming a document" role="Contracts administrator" />
            <FormGrid min={160}>
              <Field label="Supplier"><Input label="Supplier" value={p.supplier} onChange={(v) => setP({ ...p, supplier: v })} /></Field>
              {Object.entries(p.fields).filter(([k]) => k !== "total").map(([k, v]) => (
                <Field key={k} label={k.replace(/_/g, " ")} flag={k === "job" && v && v !== job ? "warning" : undefined}
                  hint={k === "job" && v && v !== job ? `This register is job ${job}.` : undefined}>
                  <Input label={k} value={v} type={k.includes("date") || k === "effective_from" ? "date" : "text"} onChange={setField(k)} />
                </Field>
              ))}
            </FormGrid>
            {p.kind === "docket" && (
              <Field label="Pour or bar schedule this docket belongs to" hint="Its quantity rolls up to the budget line through this link.">
                <Choice label="Delivery" value={p.suggested_delivery_id || ""} onChange={(v) => setP({ ...p, suggested_delivery_id: v })}
                  options={[{ value: "", label: "Choose..." }, ...(p.candidates || []).map((c) => ({ value: c.delivery_id, label: `${fmtDate(c.scheduled_date)} ${c.description} (${c.dockets} docket${c.dockets === 1 ? "" : "s"} so far)` }))]} />
              </Field>
            )}
            {p.kind === "invoice" && (
              <>
                <SectionTitle>Lines, pre-matched by docket number</SectionTitle>
                <Table rows={p.lines.map((l, i) => ({ ...l, i }))} maxHeight={300} columns={[
                  { key: "docket_no", label: "Docket", render: (r) => <Input label={`Line ${r.i + 1} docket`} value={r.docket_no} style={{ width: 120 }} onChange={(v) => setP({ ...p, lines: p.lines.map((x, j) => (j === r.i ? { ...x, docket_no: v, prematch: null } : x)) })} /> },
                  { key: "description", label: "Description", wrap: true },
                  { key: "qty", label: "Qty", align: "right" }, { key: "rate", label: "Rate", align: "right" }, { key: "amount", label: "Amount", align: "right" },
                  { key: "prematch", label: "On the register", render: (r) => (r.prematch ? <Badge tone="good">{r.prematch.delivery}</Badge> : r.docket_no ? <Badge tone="critical">Not found</Badge> : <Badge tone="neutral">Charge</Badge>) },
                ]} />
                <p style={{ fontSize: 12, color: t.textMuted }}>Reconciliation runs when you confirm. An unmatched line does not block the invoice - it turns it amber or red, which is the point.</p>
              </>
            )}
            {p.kind === "quote" && (
              <>
                <SectionTitle>Rates</SectionTitle>
                <Table rows={p.rates.map((r, i) => ({ ...r, i }))} columns={[{ key: "kind", label: "Kind" }, { key: "item", label: "Item" }, { key: "unit", label: "Unit" },
                  { key: "rate", label: "Rate ($)", render: (r) => <Input label={`Rate ${r.i + 1}`} value={r.rate} style={{ width: 100 }} onChange={(v) => setP({ ...p, rates: p.rates.map((x, j) => (j === r.i ? { ...x, rate: v } : x)) })} /> }]} />
                <p style={{ fontSize: 12, color: t.textMuted }}>Each new rate closes the one it replaces the day before it starts, so old and new prices coexist.</p>
              </>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

// ----------------------------------------------------------- project view --
function DeleteCell({ kind, row, deleted, onChange }) {
  const toast = useToast();
  if (!canWrite()) return null;
  const go = async (restore) => {
    try {
      await apiWrite("/api/msr/delete", { kind, id: row, restore });
      onChange();
      if (!restore) toast(`${row} deleted. It is kept, hidden from the totals.`, { tone: "neutral", action: { label: "Undo", run: () => go(true) } });
    } catch (e) { toast(e.message, { tone: "critical", ms: 9000 }); }
  };
  return deleted
    ? <Button icon={Undo2} onClick={() => go(true)}>Restore</Button>
    : <button type="button" aria-label={`Delete ${row}`} onClick={() => window.confirm(`Delete ${row}? You can undo it.`) && go(false)}
      style={{ border: "none", background: "none", cursor: "pointer", color: "inherit", opacity: 0.6 }}><Trash2 size={14} /></button>;
}

function ForecastEditor({ line, register, onDone }) {
  const { t } = useTheme();
  const toast = useToast();
  const [qty, setQty] = useState(String(line.fac_qty));
  const [rate, setRate] = useState(String(line.fac_rate));
  const [reason, setReason] = useState("");
  const [measure, setMeasure] = useState(false);
  const [error, setError] = useState(null);
  const save = async () => {
    setError(null);
    try {
      await apiWrite(`/api/msr/budget-lines/${line.line_id}/forecast`, { fac_qty: qty, fac_rate: rate, reason });
      toast(`Forecast for ${line.element} changed. The reason is in the audit log.`, { tone: "good" });
      onDone(true);
    } catch (e) { setError(e); }
  };
  return (
    <div style={{ background: t.surfaceRaised, border: `1px solid ${t.border}`, borderRadius: 10, padding: 12, margin: "8px 0" }}>
      <ErrorNote error={error} />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
        <Field label={`Forecast quantity (${register === "concrete" ? "m³" : "t"})`} width={150}><Input label="Forecast quantity" value={qty} onChange={setQty} /></Field>
        <Field label="Forecast rate ($)" width={130}><Input label="Forecast rate" value={rate} onChange={setRate} /></Field>
        <Field label="Reason (required)" width={320}><Input label="Reason for the change" value={reason} onChange={setReason} placeholder="e.g. Footing sizes increased on revision C drawings" /></Field>
        <Button icon={Ruler} onClick={() => setMeasure(true)}>Measure PDF</Button>
        <CTAButton onClick={save}>Save forecast</CTAButton>
        <Button onClick={() => onDone(false)}>Cancel</Button>
      </div>
      <MeasureTool open={measure} onClose={() => setMeasure(false)} register={register} line={line} onUse={(q, why) => { setQty(q); setReason(why); setMeasure(false); }} />
    </div>
  );
}

function Workspace({ job, register, tab, setRegister, setTab, onBack }) {
  const { t } = useTheme();
  const toast = useToast();
  const parts = useChartParts();
  const { data, error, reload } = useApi(`/api/msr/projects/${job}?register=${register}`);
  const [review, setReview] = useState(null);
  const [help, setHelp] = useState(false);
  const [editing, setEditing] = useState(null);
  const [showDeleted, setShowDeleted] = useState(false);
  const [invoice, setInvoice] = useState(null);
  const [formError, setFormError] = useState(null);
  const [lineForm, setLineForm] = useState({ element: "", sub_element: "", qty: "", rate: "" });
  const [priceForm, setPriceForm] = useState({ supplier: "", kind: "base", item: "", unit: "", rate: "", waived: false, effective_from: "" });
  const [delForm, setDelForm] = useState({ line_id: "", description: "", supplier: "", item: "", scheduled_date: "", planned_qty: "" });
  const { data: invoiceDetail } = useApi(invoice ? `/api/msr/invoices/${invoice}` : null);
  const visible = (rows) => rows.filter((r) => showDeleted || !r.deleted_at);
  const unit = register === "concrete" ? "m3" : "t";
  const q = (v) => fmtQty(v, unit, 2);
  const submit = async (path, body, reset, msg) => {
    setFormError(null);
    try { await apiWrite(path, { project_id: job, register, ...body }); reset(); toast(msg, { tone: "good" }); reload(); } catch (e) { setFormError(e); }
  };
  const upload = async (file) => {
    const form = new FormData();
    form.append("register", register);
    form.append("file", file);
    try { const res = await apiUpload(`/api/msr/projects/${job}/upload`, form); reload(); setReview(res.doc_id); } catch (e) { toast(e.message, { tone: "critical", ms: 9000 }); }
  };
  const del = (kind, key) => ({ key: "del", label: "", align: "right", render: (r) => <DeleteCell kind={kind} row={r[key]} deleted={Boolean(r.deleted_at)} onChange={reload} /> });
  const greyed = (r, v) => <span style={{ opacity: r.deleted_at ? 0.45 : 1, textDecoration: r.deleted_at ? "line-through" : "none" }}>{v}</span>;

  const weeks = useMemo(() => (data?.dashboard.weeks || []).map((w) => ({ ...w, label: fmtDate(w.week).slice(0, 5) })), [data]);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const d = data.dashboard;
  const meta = data.meta;

  const tabs = {
    dashboard: () => (
      <>
        <Grid cols={4} min={170}>
          <Stat label="Budget (locked)" value={fmtAud(d.budget, { short: true })} sub={q(d.budget_qty)} />
          <Stat label="Forecast at completion" value={fmtAud(d.fac, { short: true })} emphasis tone={d.fac > d.budget ? "warning" : undefined}
            sub={`${fmtAud(d.fac_vs_budget, { short: true, signed: true })} against budget, ${q(d.fac_qty)}`} />
          <Stat label="Delivered so far" value={q(d.delivered_qty)} sub={`${fmtAud(d.delivered_value, { short: true })} at forecast rates`} />
          <Stat label="Invoiced" value={fmtAud(d.invoiced, { short: true })} sub={`${d.recon.green} green, ${d.recon.amber} amber, ${d.recon.red} red`}
            tone={d.recon.red ? "critical" : d.recon.amber ? "warning" : undefined} />
        </Grid>
        {d.over_forecast.length > 0 && (
          <Callout tone="warning" title="Delivered past the forecast">
            {d.over_forecast.join(", ")}: more has been delivered than the forecast at completion allows. Either the forecast is stale or something is being over-ordered.
          </Callout>
        )}
        {d.recon.red + d.recon.amber > 0 && (
          <Callout tone="critical" title={`${d.recon.red + d.recon.amber} invoice(s) need a look`}>
            Open the Invoices tab: each one names the lines that do not reconcile and why.
          </Callout>
        )}
        <Callout tone="neutral" title="Both registers, in dollars only">
          Budget {fmtAud(d.combined.budget)}, forecast {fmtAud(d.combined.fac)}, invoiced {fmtAud(d.combined.invoiced)} across concrete and reinforcement.
          Quantities are never added across the two: cubic metres and tonnes do not sum.
        </Callout>
        <SectionTitle>Week by week</SectionTitle>
        <Card hint={`Planned against delivered ${meta.unit === "m3" ? "cubic metres" : "tonnes"}, by the week each ${meta.delivery.toLowerCase()} was scheduled.`}>
          <ChartOrTable
            chart={(
              <ChartFrame height={240}>
                <BarChart data={weeks} margin={{ left: 6, right: 10, top: 6 }}>
                  {parts.grid}
                  {parts.xAxis({ dataKey: "label", interval: "preserveStartEnd" })}
                  {parts.yAxis({})}
                  {parts.tooltip({ formatter: (v) => q(v) })}
                  {parts.legend()}
                  <Bar dataKey="planned" name="Planned" fill={t.series[2]} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="delivered" name="Delivered" fill={t.series[0]} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ChartFrame>
            )}
            table={<Table rows={weeks} columns={[{ key: "week", label: "Week of", render: (r) => fmtDate(r.week) }, { key: "events", label: `${meta.delivery}s`, align: "right" },
              { key: "planned", label: "Planned", align: "right", render: (r) => q(r.planned) }, { key: "delivered", label: "Delivered", align: "right", render: (r) => q(r.delivered) }]} />}
          />
        </Card>
      </>
    ),
    tracking: () => (
      <>
        <Card pad={0} rule={false}>
          <Table rows={visible(data.tracking)} maxHeight={560} columns={[
            { key: "element", label: "Element", wrap: true, render: (r) => greyed(r, <><b>{r.element}</b><div style={{ fontSize: 12, color: t.textMuted }}>{r.sub_element}</div></>) },
            { key: "budget", label: "Budget", align: "right", render: (r) => greyed(r, <>{q(r.budget_qty)}<div style={{ fontSize: 12, color: t.textMuted }}>{fmtAud(r.budget_amount)} at {fmtAud(r.budget_rate, { decimals: 2 })}</div></>) },
            { key: "fac", label: "Forecast at completion", align: "right", render: (r) => greyed(r, <>{q(r.fac_qty)}<div style={{ fontSize: 12, color: t.textMuted }}>{fmtAud(r.fac_amount)}</div></>) },
            { key: "delivered", label: "Delivered", align: "right", render: (r) => greyed(r, <span style={{ color: r.delivered_qty > r.fac_qty ? t.status.critical : t.text, fontWeight: r.delivered_qty > r.fac_qty ? 700 : 400 }}>{q(r.delivered_qty)}</span>) },
            { key: "pct", label: "Of forecast", align: "right", render: (r) => (r.fac_qty ? `${Math.round((r.delivered_qty / r.fac_qty) * 100)}%` : "-") },
            { key: "edit", label: "", render: (r) => !r.deleted_at && canWrite() && <Button onClick={() => setEditing(editing === r.line_id ? null : r.line_id)}>Change forecast</Button> },
            del("budget_line", "line_id"),
          ]} />
        </Card>
        {editing && <ForecastEditor key={editing} line={data.tracking.find((l) => l.line_id === editing)} register={register} onDone={(saved) => { setEditing(null); if (saved) reload(); }} />}
        {canWrite() && (
          <Card title="Add a budget line" hint="Budget is the contract baseline and does not change after this. The forecast starts equal to it and moves with a reason." style={{ marginTop: 14 }}>
            <FormGrid min={150}>
              <Field label="Element"><Input label="Element" value={lineForm.element} onChange={(v) => setLineForm({ ...lineForm, element: v })} /></Field>
              <Field label="Sub-element"><Input label="Sub-element" value={lineForm.sub_element} onChange={(v) => setLineForm({ ...lineForm, sub_element: v })} /></Field>
              <Field label={`Quantity (${meta.unit === "m3" ? "m³" : "t"})`}><Input label="Quantity" value={lineForm.qty} onChange={(v) => setLineForm({ ...lineForm, qty: v })} /></Field>
              <Field label="Rate ($)"><Input label="Rate" value={lineForm.rate} onChange={(v) => setLineForm({ ...lineForm, rate: v })} /></Field>
            </FormGrid>
            <div style={{ marginTop: 10 }}><Button icon={Plus} onClick={() => submit("/api/msr/budget-lines", lineForm, () => setLineForm({ element: "", sub_element: "", qty: "", rate: "" }), "Budget line added.")}>Add the line</Button></div>
          </Card>
        )}
      </>
    ),
    prices: () => (
      <>
        <Card pad={0} rule={false}>
          <Table rows={visible(data.prices)} maxHeight={520} columns={[
            { key: "supplier", label: "Supplier", render: (r) => greyed(r, r.supplier) }, { key: "kind", label: "Kind", render: (r) => (r.kind === "base" ? "Base rate" : "Surcharge") },
            { key: "item", label: "Item", render: (r) => greyed(r, r.item) }, { key: "unit", label: "Unit" },
            { key: "rate", label: "Rate", align: "right", render: (r) => (r.waived ? <Badge tone="good">$0 - waived</Badge> : fmtAud(r.rate, { decimals: 2 })) },
            { key: "from", label: "From", render: (r) => fmtDate(r.effective_from) }, { key: "to", label: "To", render: (r) => (r.effective_to ? fmtDate(r.effective_to) : "open") },
            { key: "current", label: "", render: (r) => (r.current && !r.deleted_at ? <Badge tone="ai">In force today</Badge> : "") },
            { key: "src", label: "", render: (r) => r.source_doc_id && <a href={`/api/msr/documents/${r.source_doc_id}/source.pdf`} target="_blank" rel="noreferrer" style={{ color: t.accent }}>Quote</a> },
            del("price", "price_id"),
          ]} />
        </Card>
        {canWrite() && (
          <Card title="Key a rate by hand" hint="Or upload the supplier's quote and review what the parser read." style={{ marginTop: 14 }}>
            <FormGrid min={140}>
              <Field label="Supplier"><Choice label="Supplier" value={priceForm.supplier} onChange={(v) => setPriceForm({ ...priceForm, supplier: v })} options={["", ...data.suppliers]} /></Field>
              <Field label="Kind"><Choice label="Kind" value={priceForm.kind} onChange={(v) => setPriceForm({ ...priceForm, kind: v })} options={[{ value: "base", label: "Base rate" }, { value: "surcharge", label: "Surcharge" }]} /></Field>
              <Field label="Item"><Input label="Item" value={priceForm.item} onChange={(v) => setPriceForm({ ...priceForm, item: v })} /></Field>
              <Field label="Unit"><Input label="Unit" value={priceForm.unit} onChange={(v) => setPriceForm({ ...priceForm, unit: v })} placeholder={meta.unit} /></Field>
              <Field label="Rate ($)"><Input label="Price rate" value={priceForm.rate} onChange={(v) => setPriceForm({ ...priceForm, rate: v })} disabled={priceForm.waived} /></Field>
              <Field label="Effective from"><Input type="date" label="Effective from" value={priceForm.effective_from} onChange={(v) => setPriceForm({ ...priceForm, effective_from: v })} /></Field>
              <Field label="Waived"><label style={{ fontSize: 13, display: "flex", gap: 6, paddingTop: 6 }}><Input type="checkbox" label="Waived" checked={priceForm.waived} onChange={(v) => setPriceForm({ ...priceForm, waived: v })} /> Agreed at $0</label></Field>
            </FormGrid>
            <div style={{ marginTop: 10 }}><Button icon={Plus} onClick={() => submit("/api/msr/prices", priceForm, () => setPriceForm({ ...priceForm, item: "", rate: "" }), "Rate added. Invoices were re-reconciled.")}>Add the rate</Button></div>
          </Card>
        )}
      </>
    ),
    deliveries: () => (
      <>
        <Card pad={0} rule={false}>
          <Table rows={visible(data.deliveries)} maxHeight={560} columns={[
            { key: "scheduled_date", label: "Scheduled", render: (r) => greyed(r, fmtDate(r.scheduled_date)) },
            { key: "description", label: meta.delivery, wrap: true, render: (r) => greyed(r, r.description) },
            { key: "item", label: "Item" },
            { key: "planned", label: "Planned", align: "right", render: (r) => q(r.planned_qty) },
            { key: "delivered", label: "Delivered", align: "right", render: (r) => q(r.delivered_qty) },
            { key: "docket_nos", label: meta.docket === "Bar schedule" ? "Schedule" : "Dockets", wrap: true, render: (r) => <span style={{ fontSize: 12 }}>{r.docket_nos || "-"}</span> },
            { key: "status", label: "Status", render: (r) => <Badge tone={r.status === "delivered" ? "good" : r.status === "scheduled" ? "neutral" : "warning"}>{r.status}</Badge> },
            del("delivery", "delivery_id"),
          ]} />
        </Card>
        {canWrite() && (
          <Card title={`Schedule a ${meta.delivery.toLowerCase()}`} hint={register === "concrete" ? "One pour is one delivery event. Link it to its budget line so delivered quantity rolls up." : "The supplier's bar schedule is the delivery record."} style={{ marginTop: 14 }}>
            <ErrorNote error={formError} />
            <FormGrid min={150}>
              <Field label="Budget line"><Choice label="Budget line" value={delForm.line_id} onChange={(v) => setDelForm({ ...delForm, line_id: v })}
                options={[{ value: "", label: "Choose..." }, ...data.tracking.filter((l) => !l.deleted_at).map((l) => ({ value: l.line_id, label: l.element }))]} /></Field>
              <Field label="Description"><Input label="Description" value={delForm.description} onChange={(v) => setDelForm({ ...delForm, description: v })} /></Field>
              <Field label="Supplier"><Choice label="Delivery supplier" value={delForm.supplier} onChange={(v) => setDelForm({ ...delForm, supplier: v })} options={["", ...data.suppliers]} /></Field>
              <Field label="Item"><Choice label="Item" value={delForm.item} onChange={(v) => setDelForm({ ...delForm, item: v })} options={["", ...data.items]} /></Field>
              <Field label="Date"><Input type="date" label="Scheduled date" value={delForm.scheduled_date} onChange={(v) => setDelForm({ ...delForm, scheduled_date: v })} /></Field>
              <Field label={`Planned (${meta.unit === "m3" ? "m³" : "t"})`}><Input label="Planned quantity" value={delForm.planned_qty} onChange={(v) => setDelForm({ ...delForm, planned_qty: v })} /></Field>
            </FormGrid>
            <div style={{ marginTop: 10 }}><Button icon={Plus} onClick={() => submit("/api/msr/deliveries", delForm, () => setDelForm({ line_id: "", description: "", supplier: "", item: "", scheduled_date: "", planned_qty: "" }), "Scheduled.")}>Schedule it</Button></div>
          </Card>
        )}
      </>
    ),
    invoices: () => (
      <>
        <Callout tone="neutral">
          Every line is checked against the register, not the invoice total: the docket must be on a {meta.delivery.toLowerCase()}, billed once, at the rate in force on the delivery date.
          Green is balanced; amber is 1 to 5% out or has an open line; red is more than 5% out. Select an invoice for its lines.
        </Callout>
        <Card pad={0} rule={false}>
          <Table rows={visible(data.invoices)} maxHeight={560} onRowClick={(r) => setInvoice(r.invoice_id)} columns={[
            { key: "invoice_no", label: "Invoice", render: (r) => greyed(r, <b>{r.invoice_no}</b>) }, { key: "supplier", label: "Supplier" },
            { key: "invoice_date", label: "Date", render: (r) => fmtDate(r.invoice_date) },
            { key: "total", label: "Invoiced", align: "right", render: (r) => fmtAud(r.total, { decimals: 2 }) },
            { key: "expected", label: "Expected", align: "right", render: (r) => fmtAud(r.expected, { decimals: 2 }) },
            { key: "variance", label: "Variance", align: "right", render: (r) => `${fmtAud(r.variance, { decimals: 2, signed: true })} (${Number(r.variance_pct).toFixed(1)}%)` },
            { key: "open_lines", label: "Open lines", align: "right" },
            { key: "recon_status", label: "Status", render: (r) => <ReconBadge status={r.recon_status} /> },
            { key: "pdf", label: "", render: (r) => <a href={`/api/msr/invoices/${r.invoice_id}/source.pdf`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} style={{ color: t.accent, display: "inline-flex", gap: 4, alignItems: "center" }}><FileText size={13} />PDF</a> },
            del("invoice", "invoice_id"),
          ]} />
        </Card>
        <Modal open={Boolean(invoice)} onClose={() => setInvoice(null)} width={980} title={invoiceDetail ? `${invoiceDetail.invoice_no} - ${invoiceDetail.supplier}` : "Invoice"}>
          {invoiceDetail && (
            <>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
                <ReconBadge status={invoiceDetail.recon_status} />
                <span style={{ fontSize: 13 }}>Invoiced {fmtAud(invoiceDetail.total, { decimals: 2 })} against {fmtAud(invoiceDetail.expected, { decimals: 2 })} expected</span>
                <a href={`/api/msr/invoices/${invoiceDetail.invoice_id}/source.pdf`} target="_blank" rel="noreferrer" style={{ color: t.accent, fontWeight: 650 }}>Source PDF</a>
              </div>
              <Table rows={invoiceDetail.lines} maxHeight={480} columns={[
                { key: "line_no", label: "#" }, { key: "docket_no", label: "Docket", render: (r) => r.docket_no || "-" }, { key: "description", label: "Description", wrap: true },
                { key: "qty", label: "Qty", align: "right" }, { key: "rate", label: "Rate", align: "right", render: (r) => fmtAud(r.rate, { decimals: 2 }) },
                { key: "amount", label: "Amount", align: "right", render: (r) => fmtAud(r.amount, { decimals: 2 }) },
                { key: "expected", label: "Expected", align: "right", render: (r) => fmtAud(r.expected, { decimals: 2 }) },
                { key: "match_status", label: "Check", render: (r) => <Badge tone={MATCH[r.match_status]?.[1] || "neutral"}>{MATCH[r.match_status]?.[0] || r.match_status}</Badge> },
                { key: "delivery", label: "Delivery", wrap: true, render: (r) => r.delivery || "-" },
              ]} />
            </>
          )}
        </Modal>
      </>
    ),
    audit: () => (
      <Card pad={0} rule={false}>
        <Table rows={data.audit} maxHeight={640} columns={[
          { key: "ts", label: "When", render: (r) => `${fmtDate(r.ts)} ${String(r.ts).slice(11, 16)}` }, { key: "actor", label: "Who" },
          { key: "action", label: "What", render: (r) => <span style={{ textTransform: "capitalize" }}>{r.action}</span> }, { key: "subject", label: "Record", wrap: true },
          { key: "outcome", label: "", render: (r) => (r.outcome === "refused" ? <Badge tone="critical">Refused</Badge> : <Badge tone="good">Recorded</Badge>) },
          { key: "detail", label: "Detail", wrap: true, render: (r) => <>{r.detail}{r.reason && <div style={{ color: t.textMuted, fontSize: 12 }}>Reason: {r.reason}</div>}</> },
        ]} />
      </Card>
    ),
  };

  return (
    <>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 14 }}>
        <Button icon={ArrowLeft} onClick={onBack}>Portfolio</Button>
        <div style={{ fontSize: 15, fontWeight: 700 }}>{data.project.project_id} {data.project.name}</div>
        <div style={{ flex: 1 }} />
        <SegmentedControl label="Register" value={register} onChange={setRegister}
          options={[{ value: "concrete", label: "Concrete Supply" }, { value: "reo", label: "Reinforcement Supply" }]} />
        <Button icon={CircleHelp} onClick={() => setHelp(true)}>?</Button>
      </div>
      <ReadOnlyNotice what="changing a register" role="Contracts administrator" />
      {data.inbox.length > 0 && (
        <Card title={<span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><Inbox size={15} /> Supplier paperwork to review ({data.inbox.length})</span>}
          hint="Received and read, not yet recorded. Nothing a parser reads reaches the register until a person confirms it." style={{ marginBottom: 14 }}>
          <Table rows={data.inbox} columns={[
            { key: "kind", label: "Type", render: (r) => <span style={{ textTransform: "capitalize" }}>{r.kind}</span> }, { key: "supplier", label: "Supplier" },
            { key: "register", label: "Register", render: (r) => (r.register === "concrete" ? "Concrete" : "Reinforcement") },
            { key: "filename", label: "File", wrap: true }, { key: "received_at", label: "Received", render: (r) => fmtDate(r.received_at) },
            { key: "go", label: "", render: (r) => <Button onClick={() => { if (r.register !== register) setRegister(r.register); setReview(r.doc_id); }}>Review</Button> },
          ]} />
        </Card>
      )}
      <MountedTabs value={tab} onChange={setTab} tabs={TABS.map(([key, label]) => ({ key, label, render: tabs[key] }))} right={(
        <div style={{ display: "flex", gap: 8, alignItems: "center", paddingBottom: 4 }}>
          <label style={{ fontSize: 12, color: t.textMuted, display: "flex", gap: 5, alignItems: "center" }}>
            <input type="checkbox" checked={showDeleted} onChange={(e) => setShowDeleted(e.target.checked)} /> Show deleted
          </label>
          {canWrite() && (
            <label style={{ display: "inline-flex", gap: 6, alignItems: "center", fontSize: 12, fontWeight: 650, color: t.accent, cursor: "pointer" }}>
              <Upload size={14} /> Upload PDF
              <input type="file" accept="application/pdf" hidden onChange={(e) => e.target.files[0] && upload(e.target.files[0])} />
            </label>
          )}
        </div>
      )} />
      <ReviewDialog docId={review} onClose={() => setReview(null)} onCommitted={reload} />
      <Walkthrough open={help} onClose={() => setHelp(false)} steps={data.walkthrough} current={tab} onGo={setTab} />
    </>
  );
}

// ---------------------------------------------------------------------- page --
export default function MaterialSupply() {
  const [params, setParams] = useSearchParams();
  const job = params.get("job");
  const register = params.get("register") || "concrete";
  const tab = params.get("tab") || "dashboard";
  const set = (patch) => setParams((p) => { for (const [k, v] of Object.entries(patch)) { if (v == null) p.delete(k); else p.set(k, v); } return p; }, { replace: true });
  return (
    <>
      <PageHeader
        title="Material Supply Register"
        brief="Turn our prototypes into rock-solid tools the whole company runs on"
        subtitle="Concrete and reinforcement for each job, from the contract budget through delivery dockets to invoice reconciliation at docket level - replacing a spreadsheet per project. Supplier PDFs are read by a parser per supplier, with a model as the fallback, and nothing is recorded until a person confirms it."
      />
      {job
        ? <Workspace job={job} register={register} tab={tab} setRegister={(r) => set({ register: r })} setTab={(k) => set({ tab: k })} onBack={() => set({ job: null, tab: null, register: null })} />
        : <Portfolio onOpen={(id, reg) => set({ job: id, register: reg || "concrete", tab: "dashboard" })} />}
      <Callout tone="neutral" title="Version 1 boundaries">
        Saving is last-write-wins, with no row locking. No approval gates: the audit log and the reconciliation status do that work.
        Nothing arrives from site apps or supplier e-ticketing portals yet - only PDFs a person reviews.
      </Callout>
    </>
  );
}
