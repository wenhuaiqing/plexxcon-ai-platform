// The front door: what is here, why, and where to start.

import { Link } from "react-router-dom";
import { Bot, ClipboardList, HardHat, Landmark, Truck } from "lucide-react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { useOrb } from "../../context/OrbContext.jsx";
import { fmtAud, fmtInt, useApi } from "../../lib/api.js";
import { Badge, Button, Callout, Card, ErrorNote, Grid, Loading, PageHeader, SectionTitle, Stat } from "../../lib/ui.jsx";

function SystemCard({ icon: Icon, title, to, what, replaces, stats, ask }) {
  const { t } = useTheme();
  return (
    <Card>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8 }}>
        <span style={{ background: t.accentGlow, color: t.accent, borderRadius: 10, padding: 8, display: "flex" }}><Icon size={18} /></span>
        <Link to={to} style={{ fontSize: 16, fontWeight: 750, color: t.text }}>{title}</Link>
      </div>
      <p style={{ fontSize: 13, lineHeight: 1.55, margin: "0 0 8px" }}>{what}</p>
      <p style={{ fontSize: 12.5, color: t.textMuted, margin: "0 0 12px" }}><b>Replaces:</b> {replaces}</p>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>{stats.map((s) => <Badge key={s} tone="neutral">{s}</Badge>)}</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Link to={to}><Button>Open {title}</Button></Link>
        {ask && <Button tone="ai" onClick={ask.run}>Ask: {ask.label}</Button>}
      </div>
    </Card>
  );
}

export default function Overview() {
  const { t } = useTheme();
  const orb = useOrb();
  const { data, error } = useApi("/api/overview");
  const { data: meta } = useApi("/api/meta");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <><PageHeader title="Overview" /><Loading /></>;
  const ask = (q) => ({ label: q, run: () => orb.openWithPrompt(q, { module: "overview" }) });
  return (
    <>
      <PageHeader
        title="An operations platform for a builder, built to show the job"
        brief="Send your resume plus one thing you've built with AI"
        subtitle="Three workflow systems of the kind a construction company runs on - tendering, labour planning, and concrete and reinforcement supply - with finance reporting over the same data, and a data agent that answers questions about all of it and shows its working. Every number on screen comes from the data; the data is synthetic."
      />
      <Callout tone="neutral" title="What this is">
        Built with AI (Claude Code) for an application to Plexxcon, and named for it. Not affiliated with or endorsed by Plexxcon; the jobs,
        suppliers, ledgers and people are invented. The three systems are rebuilds, on synthetic data, of the kind of tools I have built and
        run in production for a construction group - not copies of them, and not a guess at how Plexxcon works.
      </Callout>
      <Grid cols={4} min={180}>
        <Stat label="Workflow systems" value="3" emphasis sub="Each with its own write rules and audit trail" />
        <Stat label="Audit log entries" value={fmtInt(data.audit.entries)} sub={`${data.audit.refused} refusals recorded`} />
        <Stat label="Ledger lines" value={fmtInt(data.finance.ledger_lines)} sub={`${data.finance.entities} entities, ${data.finance.months} months`} />
        <Stat label="Data agent" value={meta?.llm_configured ? "Live" : "Catalogue"} tone={meta?.llm_configured ? undefined : "warning"}
          sub={meta?.llm_configured ? `Model ${meta.llm_model}` : "No model key on this deployment"} />
      </Grid>

      <SectionTitle>The three workflow systems</SectionTitle>
      <p style={{ fontSize: 13, margin: "0 0 12px", maxWidth: 820, lineHeight: 1.5 }}>
        Not dashboards: people do their jobs in these - draft, submit, approve, reconcile - and the rules hold whoever is acting.
        <b> Each is modelled on a system I designed and built that runs in production at a construction group.</b> The code and the
        data here are new, written for this demo. Try them: pick who you are acting as at the top.
      </p>
      <Grid cols={3} min={300}>
        <SystemCard icon={ClipboardList} title="Bid Summary" to="/bid-summary"
          what="The one-page commercial summary of a tender, with every price change locked as an immutable, numbered revision. Linked to the CRM, imports and exports the estimating workbook, renders the PDF."
          replaces="a summary spreadsheet emailed around as 'v3 final', and re-keying from the CRM."
          stats={[`${data.bids.tenders} tenders`, `${data.bids.revisions} revisions`, `${fmtAud(data.bids.open_value, { short: true })} open pipeline`]}
          ask={ask("What is our win rate by sector?")} />
        <SystemCard icon={HardHat} title="Trade Planner" to="/trade-planner"
          what="A guided wizard for a trades and labour request: tasks draw production rates from one shared library, locations generate cost codes, working days give a finish date, and a second person decides it."
          replaces="a labour spreadsheet per job, personal rate files, and approval by email."
          stats={[`${data.trades.requests} requests`, `${data.trades.awaiting} awaiting a decision`, `${data.trades.rates} library rates`]}
          ask={ask("How much approved labour budget does each job have?")} />
        <SystemCard icon={Truck} title="Material Supply Register" to="/material-supply"
          what="Concrete and reinforcement per job, from budget and forecast through pours and dockets to invoices reconciled line by line. Supplier PDFs are parsed, then confirmed by a person."
          replaces="a supply spreadsheet per project kept by a contracts administrator, and invoice checking at total level."
          stats={[`${data.msr.jobs} jobs`, `${fmtInt(data.msr.dockets)} dockets`, `${data.msr.not_green} invoices to check`, `${data.msr.inbox} PDFs in the inbox`]}
          ask={ask("Which supplier invoices are red or amber, and by how much?")} />
      </Grid>

      <SectionTitle>Over the same data</SectionTitle>
      <Grid cols={2} min={320}>
        <Card title={<span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}><Landmark size={16} /> Finance</span>}
          hint="Four entities, a general ledger shaped like an accounting-system export, consolidated with eliminations.">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link to="/profit-and-loss"><Button>Profit and Loss</Button></Link>
            <Link to="/balance-sheet"><Button>Balance Sheet</Button></Link>
            <Link to="/related-party"><Button>Related Party Balance</Button></Link>
          </div>
          <p style={{ fontSize: 12.5, color: t.textMuted, marginBottom: 0 }}>
            Three intercompany breaks are seeded in the ledger. The Related Party Balance page finds each one from the two ledgers and says why.
          </p>
        </Card>
        <Card title={<span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}><Bot size={16} /> Data agent</span>}
          hint="Ask in plain English from any page (bottom right). It writes one SQL query, a gate checks it, it runs read-only, and the answer carries the query and the rows.">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link to="/data-agent"><Button>How it works and how it is graded</Button></Link>
            <Button tone="ai" onClick={() => orb.openWithPrompt("What was group revenue this financial year to date?", { module: "overview" })}>Try a question</Button>
          </div>
        </Card>
      </Grid>

      <SectionTitle>Built the way the systems would be run</SectionTitle>
      <Grid cols={3} min={260}>
        <Card title="Each feature owns its schema">
          <p style={{ fontSize: 13, marginTop: 0 }}>Migrations live in one folder per feature, applied in order and checksummed: a migration changed after it ran stops the build.</p>
          {data.migrations.map((m) => <div key={m.feature} style={{ fontSize: 12.5 }}><b>{m.feature}</b>: {m.files} file(s)</div>)}
        </Card>
        <Card title="Every write is governed">
          <p style={{ fontSize: 13, marginTop: 0 }}>
            Token-gated, audit-logged, and refused - not warned - when a rule says no: nobody approves their own labour request, a docket cannot be
            recorded twice, a forecast cannot change without a reason, a submitted revision cannot be edited.
          </p>
        </Card>
        <Card title="The build checks itself">
          <p style={{ fontSize: 13, marginTop: 0 }}>The data is generated from a seed with integer arithmetic, then these must hold or there is no image:</p>
          <ul style={{ fontSize: 12.5, paddingLeft: 18, margin: 0 }}>{data.acceptance.map((a) => <li key={a}>{a}</li>)}</ul>
        </Card>
      </Grid>
      <p style={{ fontSize: 12, color: t.textMuted, marginTop: 16 }}>
        This is an open demo: try anything in the three workflow systems. Pick who you are acting as at the top - the rules still refuse what they should, such as approving your own request, and each refusal is in the audit log. Changes go back to the built data whenever the site has been idle.
      </p>
    </>
  );
}
