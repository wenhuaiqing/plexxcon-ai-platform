// Related Party Balance: what each entity says it is owed against what the
// other says it owes, and - where they differ - which entries make the gap.

import { useState } from "react";
import { Line, LineChart } from "recharts";
import { useTheme } from "../../context/ThemeContext.jsx";
import { fmtAud, fmtDate, fmtMonth, useApi } from "../../lib/api.js";
import Drawer from "../../components/common/Drawer.jsx";
import {
  Badge, Button, Callout, Card, ChartFrame, ChartOrTable, ErrorNote, Grid, Loading, PageHeader, SectionTitle, Select, Stat, Table, useChartParts,
} from "../../lib/ui.jsx";

const KIND = {
  one_sided: ["Booked on one side only", "critical"],
  wrong_party: ["Booked to the wrong related party", "serious"],
  wrong_party_other_half: ["Other half of a wrong-party booking", "serious"],
  timing: ["Timing - payment not yet receipted", "warning"],
  unreceipted: ["Payment never receipted", "critical"],
};

function Ledger({ pair, asAt, onClose }) {
  const { t } = useTheme();
  const { data } = useApi(pair ? `/api/finance/related-party/ledger?creditor=${pair.creditor}&debtor=${pair.debtor}&as_at=${asAt}` : null);
  const cols = [
    { key: "date", label: "Date", render: (r) => fmtDate(r.date) },
    { key: "description", label: "Entry", wrap: true },
    { key: "amount", label: "Amount", align: "right", render: (r) => fmtAud(r.amount) },
  ];
  return (
    <Drawer open={Boolean(pair)} onClose={onClose} width={620} title={pair ? `${pair.creditor} and ${pair.debtor}: both ledgers` : ""}
      subtitle={data ? `Movements since ${fmtDate(data.since)}. A charge raises the balance; a payment lowers it.` : ""}>
      {data && (
        <>
          <h3 style={{ fontSize: 13, margin: "4px 0 8px" }}>{pair.creditor_name}: receivable from {pair.debtor}</h3>
          <Table columns={cols} rows={data.creditor_ledger} maxHeight={320} />
          <h3 style={{ fontSize: 13, margin: "16px 0 8px" }}>{pair.debtor_name}: payable to {pair.creditor}</h3>
          <Table columns={cols} rows={data.debtor_ledger} maxHeight={320} />
          <p style={{ fontSize: 12, color: t.textMuted }}>Older movements agree in pairs and are left out for length.</p>
        </>
      )}
    </Drawer>
  );
}

export default function RelatedParty() {
  const { t } = useTheme();
  const { data: options } = useApi("/api/finance/options");
  const [asAt, setAsAt] = useState("");
  const { data, error } = useApi(`/api/finance/related-party${asAt ? `?as_at=${asAt}` : ""}`);
  const [open, setOpen] = useState(null);
  const parts = useChartParts();
  const right = options && <Select label="As at" value={asAt || options.latest} onChange={setAsAt} options={options.month_ends.map((m) => ({ value: m, label: fmtDate(m) }))} />;
  if (error) return <ErrorNote error={error} />;
  if (!data) return <><PageHeader title="Related Party Balance" right={right} /><Loading /></>;
  const tot = data.totals;
  const findings = data.pairs.flatMap((p) => p.findings.map((f) => ({ ...f, pair: `${p.creditor} / ${p.debtor}` })));

  return (
    <>
      <PageHeader
        title="Related Party Balance"
        brief="Kill clunky software and spreadsheet chaos, and replace them with systems we own"
        subtitle={`At ${fmtDate(data.as_at)}. For every pair of group entities: what the one says it is owed, what the other says it owes, and the difference. A difference is explained from the entries on both ledgers - the month-end check a finance team otherwise does by hand in a spreadsheet.`}
        right={right}
      />
      <Grid cols={4} min={180}>
        <Stat label="Pairs that agree" value={`${tot.pairs - tot.out_of_balance} of ${tot.pairs}`} emphasis />
        <Stat label="Pairs out of balance" value={tot.out_of_balance} tone={tot.out_of_balance ? "warning" : "good"} />
        <Stat label="Gross difference" value={fmtAud(tot.gross_difference)} tone={tot.gross_difference ? "warning" : "good"} sub="Sum of the gaps, ignoring sign" />
        <Stat label="Entries explaining it" value={findings.length} />
      </Grid>

      <SectionTitle>Between group entities</SectionTitle>
      <Card pad={0} rule={false}>
        <Table rows={data.pairs} maxHeight={600} onRowClick={setOpen} columns={[
          { key: "creditor", label: "Owed to", wrap: true, render: (r) => <><b>{r.creditor}</b> <span style={{ color: t.textMuted }}>{r.creditor_name}</span></> },
          { key: "debtor", label: "Owed by", wrap: true, render: (r) => <><b>{r.debtor}</b> <span style={{ color: t.textMuted }}>{r.debtor_name}</span></> },
          { key: "receivable", label: "Receivable per lender", align: "right", render: (r) => fmtAud(r.receivable) },
          { key: "payable", label: "Payable per borrower", align: "right", render: (r) => fmtAud(r.payable) },
          { key: "difference", label: "Difference", align: "right", render: (r) => <b>{fmtAud(r.difference)}</b> },
          { key: "agrees", label: "", render: (r) => (r.agrees ? <Badge tone="good">Agrees</Badge> : <Badge tone="warning">Out by {fmtAud(Math.abs(r.difference))}</Badge>) },
        ]} />
      </Card>
      <p style={{ fontSize: 12, color: t.textMuted, margin: "6px 0 0" }}>Select a pair to see both ledgers side by side.</p>

      {findings.length > 0 && (
        <>
          <SectionTitle>Why they differ</SectionTitle>
          <Callout tone="neutral">
            Found by pairing each charge and payment on one ledger with its counterpart on the other, by amount and within twenty days.
            What is left is listed with the reason. Fixing it is a journal - a decision for the finance team, not something this page does.
          </Callout>
          <Card pad={0} rule={false}>
            <Table rows={findings} maxHeight={500} columns={[
              { key: "pair", label: "Pair" },
              { key: "kind", label: "What", render: (r) => <Badge tone={KIND[r.kind]?.[1] || "neutral"}>{KIND[r.kind]?.[0] || r.kind}</Badge> },
              { key: "date", label: "Date", render: (r) => fmtDate(r.date) },
              { key: "amount", label: "Amount", align: "right", render: (r) => fmtAud(Math.abs(r.amount)) },
              { key: "explanation", label: "Explanation", wrap: true, render: (r) => <><div>{r.explanation}</div><div style={{ fontSize: 11.5, color: t.textMuted }}>{r.entry}</div></> },
            ]} />
          </Card>
        </>
      )}

      <SectionTitle>Outside the group</SectionTitle>
      <Card pad={0} rule={false}>
        <Table rows={data.outside_group} empty="No related-party balances outside the group." columns={[
          { key: "entity", label: "Entity", render: (r) => `${r.entity} ${r.entity_name}` },
          { key: "party", label: "Related party", render: (r) => r.party_name },
          { key: "receivable", label: "Receivable", align: "right", render: (r) => fmtAud(r.receivable) },
          { key: "payable", label: "Payable", align: "right", render: (r) => fmtAud(r.payable) },
          { key: "note", label: "", wrap: true, render: () => <span style={{ color: t.textMuted, fontSize: 12 }}>Not eliminated on consolidation; disclosed.</span> },
        ]} />
      </Card>

      <SectionTitle>Over time</SectionTitle>
      <Card title="Group intercompany receivables against payables" hint="The two lines should sit on top of each other. Where they part, something was booked on one side only.">
        <ChartOrTable
          chart={(
            <ChartFrame height={240}>
              <LineChart data={data.trend.map((r) => ({ ...r, month: fmtMonth(r.month_end) }))} margin={{ left: 6, right: 10, top: 6 }}>
                {parts.grid}
                {parts.xAxis({ dataKey: "month" })}
                {parts.yAxis({ tickFormatter: (v) => fmtAud(v, { short: true }) })}
                {parts.tooltip({ formatter: (v) => fmtAud(v) })}
                {parts.legend()}
                <Line dataKey="receivable" name="Receivables" stroke={t.series[0]} strokeWidth={2} dot={false} />
                <Line dataKey="payable" name="Payables" stroke={t.series[1]} strokeWidth={2} strokeDasharray="5 4" dot={false} />
              </LineChart>
            </ChartFrame>
          )}
          table={<Table rows={data.trend} columns={[{ key: "month_end", label: "Month end", render: (r) => fmtDate(r.month_end) },
            { key: "receivable", label: "Receivables", align: "right", render: (r) => fmtAud(r.receivable) },
            { key: "payable", label: "Payables", align: "right", render: (r) => fmtAud(r.payable) },
            { key: "difference", label: "Difference", align: "right", render: (r) => fmtAud(r.difference) }]} />}
        />
      </Card>
      <div style={{ marginTop: 10 }}><Button onClick={() => setOpen(data.pairs.find((p) => !p.agrees) || data.pairs[0])}>Open the largest difference</Button></div>
      <Ledger pair={open} asAt={data.as_at} onClose={() => setOpen(null)} />
    </>
  );
}
