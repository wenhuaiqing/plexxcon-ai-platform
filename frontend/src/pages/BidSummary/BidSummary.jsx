// Bid Summary: the one-page commercial summary of a tender. Every price change
// is an immutable, numbered revision. Sits on top of the estimating workbook:
// import its summary tab, paste blocks into the grids, export back.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart } from "recharts";
import {
  Download, Eye, FilePlus2, FileUp, History, Play, Plus, RotateCcw, Save, Send, Trash2, Undo2,
} from "lucide-react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { actorName } from "../../config.js";
import { api, apiBlob, apiUpload, apiWrite, fmtAud, fmtDate, fmtDateTime, fmtTime, useApi } from "../../lib/api.js";
import { totals as calcTotals, validate as calcValidate } from "../../lib/bidCalc.js";
import {
  Choice, Field, FormGrid, Input, Modal, MountedTabs, ReadOnlyNotice, canWrite, downloadBlob, readLocal, useInputStyle, useOnline,
  useToast, writeLocal,
} from "../../lib/kit.jsx";
import {
  Badge, Button, CTAButton, Callout, Card, ChartFrame, ChartOrTable, ErrorNote, Grid, KeyValues, Loading, PageHeader, SectionTitle,
  Stat, Table, useChartParts,
} from "../../lib/ui.jsx";

const SECTIONS = [
  ["project", "Project details"], ["programme", "Programme"], ["direct", "Direct costs"], ["indirect", "Indirect costs"],
  ["margin", "Margin and risk"], ["competitors", "Competitors"], ["benchmarking", "Benchmarking"],
];
const cents = (c) => fmtAud(c / 100);
const STAGE_TONE = { won: "good", lost: "neutral", submitted: "ai", tendering: "warning", qualifying: "neutral" };

// ------------------------------------------------------------------ register --
function Register({ reference, onNewFrom, reloadKey }) {
  const { t } = useTheme();
  const { data, error, reload } = useApi("/api/bids");
  const [open, setOpen] = useState(null);
  useEffect(() => { reload(); }, [reloadKey, reload]);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  return (
    <div style={{ display: "grid", gridTemplateColumns: open ? "minmax(0, 1.15fr) minmax(0, 1fr)" : "1fr", gap: 14 }}>
      <Card pad={0} rule={false}>
        <Table rows={data} maxHeight={720} onRowClick={(r) => setOpen({ bid_id: r.bid_id, revision: r.latest_revision })} columns={[
          { key: "bid_number", label: "Bid", render: (r) => <b>{r.bid_number}</b> },
          { key: "bid_name", label: "Tender", wrap: true, render: (r) => (
            <div>
              <div>{r.bid_name}</div>
              {r.in_progress && <span style={{ marginTop: 3, display: "inline-block" }}><Badge tone="warning">In progress - {r.in_progress.by}</Badge></span>}
            </div>
          ) },
          { key: "sector", label: "Sector" },
          { key: "latest_revision", label: "Rev", align: "right", render: (r) => `${r.latest_revision}` },
          { key: "final_ex", label: "Final excl. tax", align: "right", render: (r) => fmtAud(r.final_ex) },
          { key: "margin_pct", label: "Margin", align: "right", render: (r) => `${Number(r.margin_pct).toFixed(1)}%` },
          { key: "submitted_at", label: "Submitted", render: (r) => fmtDate(r.submitted_at) },
          { key: "crm_stage", label: "CRM", render: (r) => <Badge tone={STAGE_TONE[r.crm_stage] || "neutral"}>{r.crm_stage || "not linked"}</Badge> },
        ]} />
      </Card>
      {open && <RevisionViewer key={`${open.bid_id}-${open.revision}`} open={open} setOpen={setOpen} onNewFrom={onNewFrom} reference={reference} />}
      {!open && <p style={{ fontSize: 12, color: t.textMuted, margin: 0 }}>One row per tender, showing its latest revision. Select a row to read it beside its PDF.</p>}
    </div>
  );
}

function RevisionViewer({ open, setOpen, onNewFrom }) {
  const { t } = useTheme();
  const { data } = useApi(`/api/bids/${open.bid_id}/revisions/${open.revision}`);
  if (!data) return <Card><Loading /></Card>;
  const p = data.data.project;
  const g = data.data.programme;
  const tot = data.totals;
  const pdf = `/api/bids/${open.bid_id}/revisions/${open.revision}/summary.pdf`;
  return (
    <Card title={`${p.bid_number} revision ${data.revision}`} right={<Button onClick={() => setOpen(null)}>Close</Button>}
      hint={`Read-only. Submitted ${fmtDateTime(data.submitted_at, { seconds: false })} by ${data.submitted_by}.${data.is_latest ? " This is the latest revision." : ""}`}>
      <KeyValues items={[
        ["Tender", p.bid_name], ["Client", p.client], ["Sector", p.sector], ["Gross building area", `${tot.gross_building_area_m2.toLocaleString("en-AU")} m2`],
        ["Practical completion", fmtDate(g.practical_completion)], ["Final excl. tax", cents(tot.final_ex_cents)],
        ["Margin", `${(tot.margin_bp / 100).toFixed(2)}% (${cents(tot.margin_cents)})`], ["Rate per m2", cents(tot.rate_per_m2_cents)],
        data.warnings_acknowledged ? ["Submitted with advisory fields empty", data.warnings_acknowledged] : null,
      ]} />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "14px 0" }}>
        {canWrite() && data.is_latest && <CTAButton icon={FilePlus2} onClick={() => onNewFrom(open.bid_id)}>New revision from this</CTAButton>}
        <a href={pdf} target="_blank" rel="noreferrer" style={{ color: t.accent, fontWeight: 650, fontSize: 12.5, alignSelf: "center" }}>Open the PDF</a>
        <a href={`/api/bids/${open.bid_id}/revisions/${open.revision}/workbook.xlsx`} style={{ color: t.accent, fontWeight: 650, fontSize: 12.5, alignSelf: "center" }}>Export to workbook</a>
      </div>
      <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: t.textMuted, marginBottom: 6 }}>Revisions</div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {data.history.map((h) => (
          <button key={h.revision} type="button" onClick={() => setOpen({ ...open, revision: h.revision })} style={{
            border: `1px solid ${h.revision === data.revision ? t.accent : t.border}`, background: h.revision === data.revision ? t.accentGlow : "transparent",
            color: t.text, borderRadius: 8, padding: "5px 9px", fontSize: 12, cursor: "pointer", fontFamily: "inherit", textAlign: "left",
          }}>
            <b>Rev {h.revision}</b>{h.is_latest ? " (latest)" : ""}<br />
            <span style={{ color: t.textMuted }}>{fmtAud(h.final_ex, { short: true })}, {Number(h.margin_pct).toFixed(1)}%</span>
          </button>
        ))}
      </div>
      <iframe title="Revision PDF" src={pdf} style={{ width: "100%", height: 520, border: `1px solid ${t.border}`, borderRadius: 8, background: "#fff" }} />
    </Card>
  );
}

// ---------------------------------------------------------------------- form --
function CostGrid({ rows, onChange, codes, disabled, onPasteBlock }) {
  const { t } = useTheme();
  const input = useInputStyle();
  const set = (i, key, value) => onChange(rows.map((r, j) => (j === i ? { ...r, [key]: value } : r)));
  const KEYS = ["cost_code", "description", "amount"];
  const paste = (e, i, col) => {
    const text = e.clipboardData.getData("text/plain");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const block = text.replace(/\r/g, "").split("\n").filter((l, k, all) => l !== "" || k < all.length - 1).map((l) => l.split("\t"));
    const next = rows.map((r) => ({ ...r }));
    block.forEach((cells, r) => {
      const at = i + r;
      while (next.length <= at) next.push({ cost_code: "", description: "", amount: "" });
      cells.forEach((v, c) => {
        const key = KEYS[col + c];
        if (key) next[at][key] = key === "amount" ? v.replace(/[$,\s]/g, "") : v.trim();
      });
    });
    onPasteBlock(next, block.length);
  };
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 520 }}>
        <thead>
          <tr style={{ color: t.textMuted, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            <th style={{ textAlign: "left", padding: "4px 6px", width: 110 }}>Cost code</th>
            <th style={{ textAlign: "left", padding: "4px 6px" }}>Description</th>
            <th style={{ textAlign: "right", padding: "4px 6px", width: 150 }}>Amount ($)</th>
            <th style={{ width: 36 }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {KEYS.map((key, col) => (
                <td key={key} style={{ padding: "3px 4px" }}>
                  <input aria-label={`${key} row ${i + 1}`} value={r[key] ?? ""} disabled={disabled} list={key === "cost_code" ? "cost-codes" : undefined}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (key === "cost_code") {
                        const hit = codes.find((c) => c.code === v);
                        onChange(rows.map((x, j) => (j === i ? { ...x, cost_code: v, description: x.description || hit?.description || "" } : x)));
                      } else set(i, key, v);
                    }}
                    onPaste={(e) => paste(e, i, col)}
                    style={{ ...input, textAlign: key === "amount" ? "right" : "left", fontVariantNumeric: "tabular-nums" }} />
                </td>
              ))}
              <td>
                {!disabled && (
                  <button type="button" aria-label={`Remove row ${i + 1}`} onClick={() => onChange(rows.filter((_, j) => j !== i))}
                    style={{ border: "none", background: "none", color: t.textMuted, cursor: "pointer" }}><Trash2 size={14} /></button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!disabled && (
        <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
          <Button icon={Plus} onClick={() => onChange([...rows, { cost_code: "", description: "", amount: "" }])}>Add a line</Button>
          <span style={{ fontSize: 11.5, color: t.textMuted }}>Paste a block of rows straight from the workbook into any cell: code, description, amount.</span>
        </div>
      )}
    </div>
  );
}

function Banner({ tone, title, children, actions }) {
  return (
    <Callout tone={tone} title={title}>
      {children}
      {actions && <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>{actions}</div>}
    </Callout>
  );
}

function ImportDialog({ open, onClose, data, onApply }) {
  const { t } = useTheme();
  const [found, setFound] = useState(null);
  const [error, setError] = useState(null);
  const [picked, setPicked] = useState({});
  const toast = useToast();
  useEffect(() => { if (!open) { setFound(null); setError(null); setPicked({}); } }, [open]);
  const upload = async (file) => {
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiUpload("/api/bids/import", form);
      setFound(res.found);
      const p = {};
      for (const s of ["project", "programme", "margin"]) for (const k of Object.keys(res.found[s] || {})) if (String(res.found[s][k]) !== String(data[s]?.[k] ?? "")) p[`${s}.${k}`] = true;
      for (const g of ["direct", "indirect"]) if (res.found[g]) p[g] = true;
      setPicked(p);
    } catch (e) { setError(e); }
  };
  const diff = [];
  if (found) {
    for (const s of ["project", "programme", "margin"]) {
      for (const [k, v] of Object.entries(found[s] || {})) {
        const now = data[s]?.[k] ?? "";
        if (String(v) !== String(now)) diff.push({ key: `${s}.${k}`, label: k.replace(/_/g, " "), now, next: v });
      }
    }
    for (const g of ["direct", "indirect"]) {
      if (found[g]) diff.push({ key: g, label: `${g} costs (whole grid)`, now: `${(data[g] || []).length} lines`, next: `${found[g].length} lines` });
    }
  }
  const apply = () => {
    const next = JSON.parse(JSON.stringify(data));
    for (const d of diff) {
      if (!picked[d.key]) continue;
      if (d.key === "direct" || d.key === "indirect") next[d.key] = found[d.key];
      else { const [s, k] = d.key.split("."); next[s][k] = d.next; }
    }
    onApply(next);
    toast(`Applied ${diff.filter((d) => picked[d.key]).length} change(s) from the workbook.`, { tone: "good" });
    onClose();
  };
  return (
    <Modal open={open} onClose={onClose} title="Import from workbook" width={820}
      footer={found ? <><Button onClick={onClose}>Cancel</Button><CTAButton onClick={apply}>Apply the ticked changes</CTAButton></> : null}>
      <p style={{ fontSize: 13, marginTop: 0 }}>
        Reads the <b>Summary</b> tab of the estimating workbook. Nothing changes until you tick what to apply.{" "}
        <a href="/api/bids/template.xlsx" style={{ color: t.accent, fontWeight: 650 }}>Download the template</a>.
      </p>
      <input type="file" accept=".xlsx" aria-label="Workbook file" onChange={(e) => e.target.files[0] && upload(e.target.files[0])} />
      <ErrorNote error={error} />
      {found && (
        diff.length === 0 ? <Callout tone="good">The workbook matches the form. Nothing to apply.</Callout> : (
          <Table rows={diff} maxHeight={420} columns={[
            { key: "pick", label: "Apply", render: (r) => <input type="checkbox" aria-label={`Apply ${r.label}`} checked={Boolean(picked[r.key])} onChange={(e) => setPicked({ ...picked, [r.key]: e.target.checked })} /> },
            { key: "label", label: "Field", render: (r) => <span style={{ textTransform: "capitalize" }}>{r.label}</span> },
            { key: "now", label: "In the form", wrap: true, render: (r) => String(r.now) || <i style={{ color: t.textMuted }}>empty</i> },
            { key: "next", label: "In the workbook", wrap: true, render: (r) => <b>{String(r.next) || "empty"}</b> },
          ]} />
        )
      )}
    </Modal>
  );
}

function SummaryForm({ reference, start, onSubmitted }) {
  const { t } = useTheme();
  const toast = useToast();
  const online = useOnline();
  const { data: drafts, reload: reloadDrafts } = useApi("/api/bids/drafts");
  const [draft, setDraft] = useState(null);
  const [data, setData] = useState(null);
  const [savedAt, setSavedAt] = useState(null);
  const [status, setStatus] = useState("idle");
  const [conflict, setConflict] = useState(null);
  const [warnings, setWarnings] = useState(null);
  const [submitted, setSubmitted] = useState(null);
  const [recovery, setRecovery] = useState(null);
  const [others, setOthers] = useState([]);
  const [undo, setUndo] = useState(null);
  const [error, setError] = useState(null);
  const [importing, setImporting] = useState(false);
  const [preview, setPreview] = useState(null);
  const [section, setSection] = useState("project");
  const dirty = useRef(false);
  const timer = useRef(null);
  const writable = canWrite() && !submitted;
  const backupKey = draft ? `plexxcon-demo:bid-backup:${draft.draft_id}` : null;

  const load = useCallback((d) => {
    setDraft(d);
    setData(d.data);
    setSavedAt(d.updated_at);
    setSubmitted(null);
    setConflict(null);
    dirty.current = false;
    const backup = readLocal(`plexxcon-demo:bid-backup:${d.draft_id}`);
    setRecovery(backup && backup.version >= d.version && JSON.stringify(backup.data) !== JSON.stringify(d.data) ? backup : null);
  }, []);

  const begin = useCallback(async (body) => {
    setError(null);
    try {
      const d = await apiWrite("/api/bids/drafts", body);
      load(d);
      reloadDrafts();
      toast(d.resumed ? `Resumed the shared draft for ${d.data.project.bid_number}.` : "Draft started.", { tone: "good" });
    } catch (e) { setError(e); }
  }, [load, reloadDrafts, toast]);

  useEffect(() => { if (start) begin(start); }, [start, begin]);

  const resume = async (id) => {
    try { load(await api(`/api/bids/drafts/${id}`)); } catch (e) { setError(e); }
  };

  const save = useCallback(async ({ overwrite = false } = {}) => {
    if (!draft || !writable) return;
    clearTimeout(timer.current);
    setStatus("saving");
    try {
      const res = await apiWrite(`/api/bids/drafts/${draft.draft_id}`, { data, version: draft.version, overwrite }, "PUT");
      setDraft((d) => ({ ...d, version: res.version }));
      setSavedAt(res.updated_at);
      setStatus("saved");
      setConflict(null);
      dirty.current = false;
      writeLocal(backupKey, null);
    } catch (e) {
      setStatus("error");
      if (e.status === 409 && e.detail?.kind === "conflict") setConflict(e.detail);
      else setError(e);
    }
  }, [draft, data, writable, backupKey]);

  // Every keystroke: a local backup at once, the server two seconds after typing stops.
  const change = (next) => {
    setData(next);
    dirty.current = true;
    if (backupKey) writeLocal(backupKey, { data: next, version: draft.version, at: new Date().toISOString() });
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  // The timer is set after render so it calls the save that holds the new data.
  useEffect(() => {
    if (!dirty.current || !online || conflict) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => save(), 2000);
  }, [data, online]); // eslint-disable-line react-hooks/exhaustive-deps

  // Presence: who else has this draft open. Presence, not co-editing.
  useEffect(() => {
    if (!draft || !canWrite() || submitted) return undefined;
    let live = true;
    const beat = () => apiWrite(`/api/bids/drafts/${draft.draft_id}/presence`).then((o) => live && setOthers(o)).catch(() => {});
    beat();
    const id = setInterval(beat, 20_000);
    return () => { live = false; clearInterval(id); };
  }, [draft?.draft_id, submitted]); // eslint-disable-line react-hooks/exhaustive-deps

  // Section navigation follows the scroll.
  useEffect(() => {
    if (!data) return undefined;
    const io = new IntersectionObserver((entries) => {
      const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (top) setSection(top.target.dataset.section);
    }, { rootMargin: "-20% 0px -65% 0px" });
    document.querySelectorAll("[data-section]").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [Boolean(data)]); // eslint-disable-line react-hooks/exhaustive-deps

  const totals = useMemo(() => (data ? calcTotals(data) : null), [data]);
  const problems = useMemo(() => (data ? calcValidate(data, [...reference.hard_stops], reference.soft_warnings) : { hard: [], soft: [] }), [data, reference]);
  const flag = (key) => (problems.hard.some((h) => h.field === key) ? "critical" : problems.soft.some((s) => s.field === key) ? "warning" : undefined);

  const submit = async (acknowledge = false) => {
    setError(null);
    if (dirty.current) await save();
    try {
      const res = await apiWrite(`/api/bids/drafts/${draft.draft_id}/submit`, { acknowledge_warnings: acknowledge });
      setWarnings(null);
      setSubmitted(res);
      writeLocal(backupKey, null);
      reloadDrafts();
      onSubmitted(res);
      toast(`${res.bid_number} revision ${res.revision} submitted and locked.`, { tone: "good" });
    } catch (e) {
      if (e.status === 409 && e.detail?.kind === "warnings") setWarnings(e.detail);
      else setError(e);
    }
  };

  const linkCrm = async (dealId) => {
    try {
      const d = await apiWrite(`/api/bids/drafts/${draft.draft_id}/link`, { deal_id: dealId });
      load(d);
      toast(`Linked to ${d.data.project.bid_number}. This is now the shared draft for that tender.`, { tone: "good" });
    } catch (e) { setError(e); }
  };

  const discard = async () => {
    if (!window.confirm("Discard this draft? Submitted revisions are not affected.")) return;
    await apiWrite(`/api/bids/drafts/${draft.draft_id}`, {}, "DELETE");
    writeLocal(backupKey, null);
    setDraft(null);
    setData(null);
    reloadDrafts();
  };

  const set = (s, k) => (v) => change({ ...data, [s]: { ...data[s], [k]: v } });

  if (!data) {
    return (
      <>
        <ReadOnlyNotice what="creating or editing a summary" role="Estimator" />
        <ErrorNote error={error} />
        <Grid cols={3} min={260}>
          <Card title="New revision from a tender" hint="Clones the latest revision. If someone already has the tender's shared draft open, you join that draft instead.">
            <StartFrom reference={reference} onPick={(id) => begin({ bid_id: id })} />
          </Card>
          <Card title="New blank summary" hint="A private draft. It becomes the tender's shared draft when you link it to a CRM opportunity.">
            <CTAButton icon={FilePlus2} disabled={!canWrite()} onClick={() => begin({ blank: true })}>New blank summary</CTAButton>
          </Card>
          <Card title="Resume a draft" hint="Drafts survive closing the tab. A shared draft shows in the register as In progress.">
            {!drafts ? <Loading /> : drafts.length === 0 ? <p style={{ fontSize: 13, color: t.textMuted }}>No drafts open.</p> : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {drafts.map((d) => (
                  <button key={d.draft_id} type="button" onClick={() => resume(d.draft_id)} style={{
                    textAlign: "left", border: `1px solid ${t.border}`, background: t.surface, borderRadius: 8, padding: "7px 10px",
                    cursor: "pointer", fontFamily: "inherit", color: t.text, fontSize: 12.5,
                  }}>
                    <b>{d.bid_number || "Unlinked"}</b> {d.bid_name || "(blank)"}<br />
                    <span style={{ color: t.textMuted }}>{d.bid_id ? "Shared" : "Private"} - last saved {fmtDateTime(d.updated_at, { seconds: false })} by {d.updated_by}</span>
                  </button>
                ))}
              </div>
            )}
          </Card>
        </Grid>
      </>
    );
  }

  const p = data.project;
  const g = data.programme;
  const m = data.margin;
  return (
    <div>
      {/* Action header strip */}
      <div style={{
        position: "sticky", top: 0, zIndex: 5, background: t.bg, padding: "8px 0", display: "flex", gap: 8, alignItems: "center",
        flexWrap: "wrap", borderBottom: `1px solid ${t.border}`, marginBottom: 12,
      }}>
        <Button icon={FilePlus2} onClick={() => { setDraft(null); setData(null); }}>New</Button>
        <Button icon={History} onClick={() => { setDraft(null); setData(null); }}>Resume</Button>
        <Button icon={Save} disabled={!writable} onClick={() => save()}>Save snapshot</Button>
        <Button icon={FileUp} disabled={!writable} onClick={() => setImporting(true)}>Import</Button>
        <Button icon={Eye} onClick={async () => setPreview(URL.createObjectURL(await apiBlob("/api/bids/preview.pdf", { data })))}>Preview</Button>
        <Button icon={Download} onClick={async () => downloadBlob(await apiBlob("/api/bids/workbook.xlsx", { data }), `${p.bid_number || "bid-summary"}.xlsx`)}>Export to my workbook</Button>
        <CTAButton icon={Send} disabled={!writable} onClick={() => submit(false)}>Submit</CTAButton>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: t.textMuted }}>
          {status === "saving" ? "Saving..." : savedAt ? `Autosaved ${fmtTime(savedAt, { seconds: false })}` : ""}
        </span>
        {others.length > 0 && <Badge tone="warning">Also editing: {others.map((o) => o.actor).join(", ")}</Badge>}
        <span style={{ fontSize: 12, color: t.textMuted }}>{draft.bid_id ? "Shared draft" : "Private draft"} {draft.draft_id}</span>
      </div>

      {/* Contextual banners */}
      <ReadOnlyNotice what="editing or submitting" role="Estimator" />
      <ErrorNote error={error} />
      {!online && <Banner tone="warning" title="Offline">Changes are kept in this browser and will save when the connection returns.</Banner>}
      {submitted && (
        <Banner tone="good" title={`Submitted as ${submitted.bid_number} revision ${submitted.revision}`}>
          The revision is locked and flagged Latest, its PDF is archived and the audit log has the entry. This draft is retired; the form is read-only.
        </Banner>
      )}
      {conflict && (
        <Banner tone="critical" title="Save conflict" actions={<>
          <Button onClick={() => save({ overwrite: true })}>Keep mine (overwrite theirs)</Button>
          <Button onClick={() => { load({ ...conflict.theirs, data: conflict.theirs.data }); toast("Took their copy. Your edits were discarded.", { tone: "neutral" }); }}>Take theirs</Button>
        </>}>
          {conflict.message} Choose which copy to keep - the last save never silently wins. Whichever you choose is recorded in the audit log.
        </Banner>
      )}
      {recovery && (
        <Banner tone="warning" title="Unsaved changes found in this browser" actions={<>
          <Button onClick={() => { change(recovery.data); setRecovery(null); }}>Restore them</Button>
          <Button onClick={() => { writeLocal(backupKey, null); setRecovery(null); }}>Discard them</Button>
        </>}>
          This browser kept edits from {fmtDateTime(recovery.at, { seconds: false })} that never reached the server.
        </Banner>
      )}
      {draft.updated_by !== actorName() && !submitted && !conflict && (
        <Banner tone="neutral" title="Draft handoff">Last saved by {draft.updated_by}. Your next save takes the draft over, and the handoff is recorded.</Banner>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(150px, 190px) minmax(0, 1fr)", gap: 18, alignItems: "start" }} className="bid-form">
        <nav aria-label="Form sections" style={{ position: "sticky", top: 50, display: "flex", flexDirection: "column", gap: 2 }}>
          {SECTIONS.map(([key, label]) => (
            <a key={key} href={`#bid-${key}`} onClick={(e) => { e.preventDefault(); document.getElementById(`bid-${key}`)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}
              style={{ fontSize: 12.5, padding: "6px 10px", borderRadius: 7, color: section === key ? t.text : t.textMuted, fontWeight: section === key ? 700 : 500,
                background: section === key ? t.accentGlow : "transparent", borderLeft: `2px solid ${section === key ? t.brand : "transparent"}` }}>
              {label}
            </a>
          ))}
        </nav>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
          <section id="bid-project" data-section="project"><Card title="Project details" right={writable && (
            <Choice label="Link to CRM opportunity" value={draft.deal_id || ""} onChange={(v) => v && linkCrm(v)} style={{ width: 280 }}
              options={[{ value: "", label: draft.deal_id ? "Linked" : "Link to a CRM opportunity..." },
                ...reference.crm.deals.map((d) => ({ value: d.deal_id, label: `${d.bid_number} ${d.dealname} (${d.dealstage})` }))]} />
          )}>
            <FormGrid>
              <Field label="Bid Name" flag={flag("bid_name")}><Input label="Bid Name" value={p.bid_name} onChange={set("project", "bid_name")} disabled={!writable} /></Field>
              <Field label="Bid Number" flag={flag("bid_number")}><Input label="Bid Number" value={p.bid_number} onChange={set("project", "bid_number")} disabled={!writable || Boolean(draft.deal_id)} /></Field>
              <Field label="Sector"><Choice label="Sector" value={p.sector} onChange={set("project", "sector")} disabled={!writable} options={["", ...reference.sectors]} /></Field>
              <Field label="Client"><Input label="Client" value={p.client} onChange={set("project", "client")} disabled={!writable} /></Field>
              <Field label="Location"><Input label="Location" value={p.location} onChange={set("project", "location")} disabled={!writable} /></Field>
              <Field label="Gross Building Area (m2)" flag={flag("gross_building_area")}><Input label="Gross Building Area" value={p.gross_building_area} onChange={set("project", "gross_building_area")} disabled={!writable} /></Field>
              <Field label="Bid Gate" flag={flag("bid_gate")}><Choice label="Bid Gate" value={p.bid_gate} onChange={set("project", "bid_gate")} disabled={!writable} options={["", ...reference.bid_gates]} /></Field>
              <Field label="Estimator"><Input label="Estimator" value={p.estimator} onChange={set("project", "estimator")} disabled={!writable} /></Field>
            </FormGrid>
          </Card></section>
          <section id="bid-programme" data-section="programme"><Card title="Programme">
            <FormGrid>
              <Field label="Submission Date" flag={flag("submission_date")}><Input type="date" label="Submission Date" value={g.submission_date} onChange={set("programme", "submission_date")} disabled={!writable} /></Field>
              <Field label="Contract Execution" flag={flag("contract_execution")}><Input type="date" label="Contract Execution" value={g.contract_execution} onChange={set("programme", "contract_execution")} disabled={!writable} /></Field>
              <Field label="Site Establishment" flag={flag("site_establishment")}><Input type="date" label="Site Establishment" value={g.site_establishment} onChange={set("programme", "site_establishment")} disabled={!writable} /></Field>
              <Field label="Practical Completion Date" flag={flag("practical_completion")}><Input type="date" label="Practical Completion Date" value={g.practical_completion} onChange={set("programme", "practical_completion")} disabled={!writable} /></Field>
              <Field label="Included Delays (days)" flag={flag("included_delays")}><Input label="Included Delays" value={g.included_delays} onChange={set("programme", "included_delays")} disabled={!writable} /></Field>
            </FormGrid>
          </Card></section>
          {["direct", "indirect"].map((grid) => (
            <section key={grid} id={`bid-${grid}`} data-section={grid}>
              <Card title={grid === "direct" ? "Direct costs" : "Indirect costs"} right={undo?.grid === grid && (
                <Button icon={Undo2} onClick={() => { change({ ...data, [grid]: undo.rows }); setUndo(null); }}>Undo paste</Button>
              )}>
                <CostGrid rows={data[grid]} codes={reference.cost_codes} disabled={!writable}
                  onChange={(rows) => change({ ...data, [grid]: rows })}
                  onPasteBlock={(rows, n) => { setUndo({ grid, rows: data[grid] }); change({ ...data, [grid]: rows }); toast(`Pasted ${n} row(s).`, { tone: "good", action: { label: "Undo", run: () => change({ ...data, [grid]: data[grid] }) } }); }} />
                <div style={{ textAlign: "right", fontWeight: 700, marginTop: 8 }}>Total {grid}: {cents(grid === "direct" ? totals.direct_cents : totals.indirect_cents)}</div>
              </Card>
            </section>
          ))}
          <section id="bid-margin" data-section="margin"><Card title="Margin and risk">
            <FormGrid>
              <Field label="Contingency %"><Input label="Contingency %" value={m.contingency_pct} onChange={set("margin", "contingency_pct")} disabled={!writable} /></Field>
              <Field label="Escalation ($)"><Input label="Escalation" value={m.escalation} onChange={set("margin", "escalation")} disabled={!writable} /></Field>
              <Field label="Margin %"><Input label="Margin %" value={m.margin_pct} onChange={set("margin", "margin_pct")} disabled={!writable} /></Field>
            </FormGrid>
            <KeyValues columns={3} items={[["Contingency", cents(totals.contingency_cents)], ["Margin", cents(totals.margin_cents)], ["GST", cents(totals.gst_cents)]]} />
          </Card></section>
          <section id="bid-competitors" data-section="competitors"><Card title="Competitors">
            {(data.competitors || []).map((c, i) => (
              <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                <Input label={`Competitor ${i + 1}`} value={c.name} disabled={!writable} onChange={(v) => change({ ...data, competitors: data.competitors.map((x, j) => (j === i ? { ...x, name: v } : x)) })} style={{ maxWidth: 220 }} />
                <Input label={`Note ${i + 1}`} value={c.note} disabled={!writable} onChange={(v) => change({ ...data, competitors: data.competitors.map((x, j) => (j === i ? { ...x, note: v } : x)) })} />
                {writable && <button type="button" aria-label="Remove competitor" onClick={() => change({ ...data, competitors: data.competitors.filter((_, j) => j !== i) })} style={{ border: "none", background: "none", color: t.textMuted, cursor: "pointer" }}><Trash2 size={14} /></button>}
              </div>
            ))}
            {writable && <Button icon={Plus} onClick={() => change({ ...data, competitors: [...(data.competitors || []), { name: "", note: "" }] })}>Add a competitor</Button>}
          </Card></section>
          <section id="bid-benchmarking" data-section="benchmarking"><Card title="Benchmarking">
            <FormGrid>
              <Field label="Comparable"><Input label="Comparable" value={data.benchmarking?.comparable} onChange={set("benchmarking", "comparable")} disabled={!writable} /></Field>
              <Field label="Notes"><Input label="Benchmark notes" value={data.benchmarking?.notes} onChange={set("benchmarking", "notes")} disabled={!writable} /></Field>
            </FormGrid>
            <p style={{ fontSize: 12.5, color: t.textMuted }}>Rate per m2 of gross building area: <b style={{ color: t.text }}>{totals.rate_per_m2_cents ? cents(totals.rate_per_m2_cents) : "needs the area"}</b></p>
            {writable && <Button icon={Trash2} onClick={discard}>Discard this draft</Button>}
          </Card></section>
          <div style={{ height: 40 }} />
        </div>
      </div>

      {/* Sticky totals footer */}
      <div style={{
        position: "sticky", bottom: -110, zIndex: 5, background: t.statHeroBg, color: t.statHeroText, borderRadius: 12, padding: "10px 16px",
        display: "flex", gap: 22, flexWrap: "wrap", alignItems: "center", fontSize: 13,
      }}>
        <span>Grand total <b style={{ fontSize: 15 }}>{cents(totals.grand_total_cents)}</b></span>
        <span>Final excl. tax <b style={{ fontSize: 15 }}>{cents(totals.final_ex_cents)}</b></span>
        <span>Final incl. tax <b style={{ fontSize: 15 }}>{cents(totals.final_inc_cents)}</b></span>
        <span style={{ flex: 1 }} />
        <span style={{ color: t.statHeroMuted }}>
          {problems.hard.length ? `${problems.hard.length} required field(s) missing` : "Required fields complete"}
          {problems.soft.length ? `, ${problems.soft.length} advisory` : ""}
        </span>
      </div>

      <ImportDialog open={importing} onClose={() => setImporting(false)} data={data} onApply={change} />
      <Modal open={Boolean(warnings)} onClose={() => setWarnings(null)} title="Advisory fields are empty"
        footer={<><Button onClick={() => setWarnings(null)}>Go back and fill them</Button><CTAButton onClick={() => submit(true)}>Submit anyway</CTAButton></>}>
        <p style={{ fontSize: 13, marginTop: 0 }}>These do not block a submission, but the revision will record that it went without them:</p>
        <ul style={{ fontSize: 13 }}>{(warnings?.soft || []).map((s) => <li key={s.field}>{s.label}</li>)}</ul>
      </Modal>
      <Modal open={Boolean(preview)} onClose={() => { URL.revokeObjectURL(preview); setPreview(null); }} title="PDF preview" width={900}>
        <iframe title="PDF preview" src={preview || undefined} style={{ width: "100%", height: "70vh", border: "none", background: "#fff" }} />
      </Modal>
      <datalist id="cost-codes">{reference.cost_codes.map((c) => <option key={c.code} value={c.code}>{c.description}</option>)}</datalist>
      <style>{"@media (max-width: 760px) { .bid-form { grid-template-columns: 1fr !important; } .bid-form > nav { display: none !important; } }"}</style>
    </div>
  );
}

function StartFrom({ reference, onPick }) {
  const { data } = useApi("/api/bids");
  const [pick, setPick] = useState("");
  if (!data) return <Loading />;
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      <Choice label="Tender" value={pick} onChange={setPick} style={{ flex: 1, minWidth: 160 }}
        options={[{ value: "", label: "Choose a tender..." }, ...data.map((b) => ({ value: b.bid_id, label: `${b.bid_number} ${b.bid_name} (rev ${b.latest_revision})` }))]} />
      <CTAButton icon={Play} disabled={!pick || !canWrite()} onClick={() => onPick(pick)}>Start</CTAButton>
      <span hidden>{reference.sections.length}</span>
    </div>
  );
}

// ------------------------------------------------------------------ insights --
function Insights({ reloadKey }) {
  const { t } = useTheme();
  const parts = useChartParts();
  const { data, reload } = useApi("/api/bids/insights");
  useEffect(() => { reload(); }, [reloadKey, reload]);
  if (!data) return <Loading />;
  const tot = data.totals;
  return (
    <>
      <p style={{ fontSize: 12.5, color: t.textMuted, marginTop: 0 }}>Bid-level figures only. Nothing here measures an individual estimator.</p>
      <Grid cols={4} min={170}>
        <Stat label="Win rate" value={tot.win_rate == null ? "-" : `${Math.round(tot.win_rate * 100)}%`} emphasis sub={`${tot.won} won, ${tot.lost} lost`} />
        <Stat label="Tenders" value={tot.bids} sub={`${tot.revisions} revisions in all`} />
        <Stat label="Open pipeline" value={fmtAud(tot.open_value, { short: true })} sub="Qualifying, tendering and submitted, from the CRM" />
        <Stat label="Repriced tenders" value={data.movement.length} sub="Submitted more than once" />
      </Grid>
      <SectionTitle>By sector</SectionTitle>
      <Card>
        <ChartOrTable
          chart={(
            <ChartFrame height={240}>
              <BarChart data={data.by_sector} margin={{ left: 6, right: 10, top: 6 }}>
                {parts.grid}
                {parts.xAxis({ dataKey: "sector" })}
                {parts.yAxis({ tickFormatter: (v) => `${v}%` })}
                {parts.tooltip({ formatter: (v) => `${Number(v).toFixed(1)}%` })}
                <Bar dataKey="avg_margin_pct" name="Average margin" fill={t.series[0]} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartFrame>
          )}
          defaultView="table"
          table={<Table rows={data.by_sector} columns={[
            { key: "sector", label: "Sector" }, { key: "bids", label: "Tenders", align: "right" }, { key: "won", label: "Won", align: "right" },
            { key: "lost", label: "Lost", align: "right" }, { key: "open", label: "Open", align: "right" },
            { key: "avg_margin_pct", label: "Average margin", align: "right", render: (r) => `${Number(r.avg_margin_pct).toFixed(1)}%` },
            { key: "avg_rate_per_m2", label: "Average $/m2", align: "right", render: (r) => fmtAud(r.avg_rate_per_m2) },
            { key: "value", label: "Value (latest revisions)", align: "right", render: (r) => fmtAud(r.value, { short: true }) },
          ]} />}
        />
      </Card>
      <SectionTitle>How prices moved between revisions</SectionTitle>
      <Card pad={0} rule={false}>
        <Table rows={data.movement} columns={[
          { key: "bid_number", label: "Bid" }, { key: "bid_name", label: "Tender", wrap: true }, { key: "revisions", label: "Revisions", align: "right" },
          { key: "first_price", label: "Revision 1", align: "right", render: (r) => fmtAud(r.first_price) },
          { key: "latest_price", label: "Latest", align: "right", render: (r) => fmtAud(r.latest_price) },
          { key: "moved", label: "Moved", align: "right", render: (r) => fmtAud(r.moved, { signed: true }) },
          { key: "margin", label: "Margin", align: "right", render: (r) => `${Number(r.first_margin_pct).toFixed(1)}% to ${Number(r.latest_margin_pct).toFixed(1)}%` },
          { key: "crm_stage", label: "Outcome", render: (r) => <Badge tone={STAGE_TONE[r.crm_stage] || "neutral"}>{r.crm_stage}</Badge> },
        ]} />
      </Card>
    </>
  );
}

export function AuditTable({ path, reloadKey, project }) {
  const { t } = useTheme();
  const { data, reload } = useApi(path);
  useEffect(() => { reload(); }, [reloadKey, reload]);
  if (!data) return <Loading />;
  return (
    <Card pad={0} rule={false}>
      <Table rows={data} maxHeight={640} empty="Nothing recorded yet." columns={[
        { key: "ts", label: "When", render: (r) => fmtDateTime(r.ts, { seconds: false }) },
        { key: "actor", label: "Who" },
        ...(project ? [{ key: "project_id", label: "Job" }] : []),
        { key: "action", label: "What", render: (r) => <span style={{ textTransform: "capitalize" }}>{r.action}</span> },
        { key: "subject", label: "Record", wrap: true },
        { key: "outcome", label: "", render: (r) => (r.outcome === "refused" ? <Badge tone="critical">Refused</Badge> : <Badge tone="good">Recorded</Badge>) },
        { key: "detail", label: "Detail", wrap: true, render: (r) => <>{r.detail}{r.reason && <div style={{ color: t.textMuted, fontSize: 12 }}>Reason: {r.reason}</div>}</> },
      ]} />
    </Card>
  );
}

// ---------------------------------------------------------------------- page --
export default function BidSummary() {
  const { data: reference, error } = useApi("/api/bids/reference");
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "register";
  const setTab = (key) => setParams((p) => { p.set("tab", key); return p; }, { replace: true });
  const [start, setStart] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  if (error) return <ErrorNote error={error} />;
  if (!reference) return <><PageHeader title="Bid Summary" /><Loading /></>;
  return (
    <>
      <PageHeader
        title="Bid Summary"
        brief="We've already built working prototypes of our own estimating, tendering, procurement and job management apps... We need someone to make them unstoppable."
        subtitle="The one-page commercial summary of a tender - cost build-up, margin, programme, competitors and benchmarks - with every price change locked as an immutable, numbered revision. It sits on top of the estimating workbook rather than replacing it: import, paste, export back."
      />
      <MountedTabs value={tab} onChange={setTab} right={<Button icon={RotateCcw} onClick={() => setReloadKey((k) => k + 1)}>Refresh</Button>} tabs={[
        { key: "register", label: "Register", render: () => <Register reference={reference} reloadKey={reloadKey} onNewFrom={(id) => { setStart({ bid_id: id, n: Date.now() }); setTab("form"); }} /> },
        { key: "form", label: "Summary Form", render: () => <SummaryForm reference={reference} start={start} onSubmitted={() => setReloadKey((k) => k + 1)} /> },
        { key: "insights", label: "Insights", render: () => <Insights reloadKey={reloadKey} /> },
        { key: "audit", label: "Audit", render: () => <AuditTable path="/api/bids/audit" reloadKey={reloadKey} /> },
      ]} />
    </>
  );
}
