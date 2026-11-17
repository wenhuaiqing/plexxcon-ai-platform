// The data agent, opened up: what it can see, the gate its SQL passes, the
// questions it knows, and how it scores against a fixed set of questions.

import { useState } from "react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { useOrb } from "../../context/OrbContext.jsx";
import { apiWrite, fmtDateTime, fmtInt, useApi } from "../../lib/api.js";
import { Badge, Button, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle, Stat, Table } from "../../lib/ui.jsx";

const ATTACKS = [
  "SELECT * FROM v_project, audit_log",
  "SELECT getenv('LLM_API_KEY')",
  "SELECT * FROM read_csv('/etc/passwd')",
  "DELETE FROM msr_invoice",
  "SELECT 1; DROP TABLE bid",
];

function Gate() {
  const { t } = useTheme();
  const [sql, setSql] = useState("SELECT job_number, recon_status, count(*) AS invoices FROM v_msr_invoice GROUP BY ALL");
  const [res, setRes] = useState(null);
  const run = async (s = sql) => { setSql(s); setRes(await apiWrite("/api/agent/gate", { sql: s })); };
  return (
    <Card title="Put a query to the gate" hint="This runs nothing; it shows what the gate would say to a query the model wrote.">
      <textarea aria-label="SQL to check" value={sql} onChange={(e) => setSql(e.target.value)} rows={3}
        style={{ width: "100%", fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 12.5, borderRadius: 8, border: `1px solid ${t.border}`, padding: 8, background: t.surface, color: t.text }} />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "8px 0" }}>
        <Button onClick={() => run()}>Check it</Button>
        {ATTACKS.map((a) => <Button key={a} onClick={() => run(a)}>{a.length > 34 ? `${a.slice(0, 33)}...` : a}</Button>)}
      </div>
      {res && (res.ok
        ? <Callout tone="good" title="Passes">Would run as: <Mono>{res.sql}</Mono></Callout>
        : <Callout tone="critical" title="Refused">{res.errors.join("; ")}</Callout>)}
    </Card>
  );
}

export default function DataAgent() {
  const { t } = useTheme();
  const orb = useOrb();
  const { data, error } = useApi("/api/agent");
  const [view, setView] = useState(null);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <><PageHeader title="Data agent" /><Loading /></>;
  const ev = data.eval;
  return (
    <>
      <PageHeader
        title="Data agent"
        brief="Connect everything: Claude, Microsoft 365/SharePoint, HubSpot, Xero, and whatever else you think will get us there"
        subtitle="Plain-English questions over the three workflow systems and the ledger. The model writes one SQL query; a gate checks it; it runs on a read-only connection with external access off; the answer carries the query, the views it read and the rows, so every figure can be checked. It proposes nothing and writes nothing."
      />
      <Grid cols={4} min={180}>
        <Stat label="Model" value={data.configured ? data.model : "None"} emphasis={data.configured} tone={data.configured ? undefined : "warning"}
          sub={data.configured ? (data.fallback_model ? `Falls back to ${data.fallback_model}` : "") : "Catalogue questions only"} />
        <Stat label="Views it can read" value={data.views.length} sub="And no base table" />
        <Stat label="Graded" value={ev ? `${ev.passed} of ${ev.total}` : "Not yet"} tone={ev ? undefined : "warning"}
          sub={ev ? `${ev.model}, ${fmtDateTime(ev.ran_at, { seconds: false })}` : "Run evals/run_agent_eval.py with a model key"} />
        <Stat label="Questions asked here" value={fmtInt(data.runs.runs)} sub={`${data.runs.by_model} by the model, ${data.runs.by_catalogue} from the catalogue`} />
      </Grid>

      <SectionTitle>How it answers</SectionTitle>
      <Grid cols={3} min={260}>
        <Card title="1. Write" hint="One SELECT over the semantic views, with the business rules a new analyst would be told: financial year, which entities eliminate, never add m3 to tonnes. Or it declines - 'the data cannot answer that' is a correct answer." />
        <Card title="2. Check" hint="SELECT only, one statement, allowlisted views only (read by DuckDB's own parser, so a comma join or subquery cannot hide a table), no function that reaches outside, a row limit. A refused query goes back to the model once with the reason." />
        <Card title="3. Run and show" hint="On a connection with external access switched off. The reply may use only figures in the rows, and the trace shows the query, the views and the row count." />
      </Grid>

      {ev && (
        <>
          <SectionTitle>How it is graded</SectionTitle>
          <Callout tone="ai" title={`${ev.passed} of ${ev.total} questions answered correctly by ${ev.model}`}>
            Each question has a reference query written by hand; the agent's rows must contain the reference answer. Questions that cannot be answered
            from the data, or that try to instruct the agent, pass only if it declines. Failures are listed, not hidden.
          </Callout>
          <Card pad={0} rule={false}>
            <Table rows={ev.cases} maxHeight={520} columns={[
              { key: "kind", label: "Kind", render: (r) => <Badge tone={r.kind === "answerable" ? "neutral" : r.kind === "adversarial" ? "critical" : "warning"}>{r.kind}</Badge> },
              { key: "question", label: "Question", wrap: true },
              { key: "passed", label: "Result", render: (r) => (r.passed ? <Badge tone="good">Pass</Badge> : <Badge tone="critical">Fail</Badge>) },
              { key: "why", label: "Why", wrap: true, render: (r) => <span style={{ fontSize: 12 }}>{r.why}</span> },
            ]} />
          </Card>
        </>
      )}

      <SectionTitle>Questions it knows by heart</SectionTitle>
      <Card hint="Each has a reference query. They are what answers when no model is configured - and the page says so when that happens.">
        <Table rows={data.known} columns={[
          { key: "question", label: "Question", wrap: true },
          { key: "sql", label: "", render: (r) => <Button onClick={() => setView(view === r.question ? null : r.question)}>{view === r.question ? "Hide SQL" : "SQL"}</Button> },
          { key: "ask", label: "", render: (r) => <Button tone="ai" onClick={() => orb.openWithPrompt(r.question, { module: "data-agent" })}>Ask it</Button> },
        ]} />
        {view && <pre style={{ fontSize: 12, whiteSpace: "pre-wrap", background: t.code, padding: 10, borderRadius: 8 }}>{data.known.find((k) => k.question === view)?.sql}</pre>}
      </Card>

      <SectionTitle>The gate</SectionTitle>
      <Gate />
      <Card title="What the gate allows" style={{ marginTop: 14 }}>
        <KeyValues items={[
          ["Views", data.gate.allowed_views.join(", ")],
          ["Forbidden keywords", data.gate.forbidden_keywords.join(", ")],
          ["Forbidden functions", data.gate.forbidden_functions.join(", ")],
          ["Row limit", `${data.gate.default_limit} added when missing; never more than ${data.gate.max_limit}`],
        ]} />
      </Card>

      <SectionTitle>What it can see</SectionTitle>
      <Grid cols={2} min={340}>
        {data.views.map((v) => (
          <Card key={v.view} title={<Mono>{v.view}</Mono>} hint={v.description}>
            <div style={{ fontSize: 11.5, color: t.textMuted, lineHeight: 1.6 }}>{v.columns.map((c) => c.name).join(", ")}</div>
          </Card>
        ))}
      </Grid>
      <SectionTitle>Rules it is given</SectionTitle>
      <Card><ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>{data.rules.map((r) => <li key={r}>{r}</li>)}</ul></Card>
      <p style={{ fontSize: 12, color: t.textMuted, marginTop: 14 }}>
        Not built: retrieval over documents (SharePoint, drawings, contracts) - the same pattern of cited answers applies, with a search index in place of the views.
        Writes by the agent - deliberately never: it can draft, a person commits.
      </p>
    </>
  );
}
