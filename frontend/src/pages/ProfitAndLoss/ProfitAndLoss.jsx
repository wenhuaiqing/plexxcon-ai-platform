// Profit and Loss: monthly, by entity or consolidated, straight from the ledger.

import { useState } from "react";
import { Bar, ComposedChart, Line } from "recharts";
import { useTheme } from "../../context/ThemeContext.jsx";
import { fmtAud, fmtDate, fmtMonth, useApi } from "../../lib/api.js";
import {
  Callout, Card, ChartFrame, ChartOrTable, ErrorNote, Grid, Loading, PageHeader, SectionTitle, Select, Stat, Table, pct, useChartParts,
} from "../../lib/ui.jsx";
import { DrillBar, DrillLink, EntriesDrawer, SectionToggle, useDrill } from "../../lib/statement.jsx";

const SECTIONS = ["Revenue", "Cost of sales", "Overheads", "Other income"];

export function EntityPicker({ options, value, onChange }) {
  return <Select label="Entity" value={value} onChange={onChange} options={(options?.entities || []).map((e) => ({ value: e.entity_id, label: e.name }))} />;
}

export default function ProfitAndLoss() {
  const { t } = useTheme();
  const { data: options } = useApi("/api/finance/options");
  const [entity, setEntity] = useState("GROUP");
  const [fy, setFy] = useState("");
  const { data, error } = useApi(`/api/finance/pnl?entity=${entity}${fy ? `&fin_year=${fy}` : ""}`);
  const parts = useChartParts();
  const drill = useDrill(SECTIONS);

  const right = options && (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      <EntityPicker options={options} value={entity} onChange={setEntity} />
      <Select label="Year" value={fy || String(options.fin_years[0])} onChange={setFy}
        options={options.fin_years.map((y) => ({ value: String(y), label: `FY${y - 1}-${String(y).slice(2)}` }))} />
    </div>
  );

  if (error) return <ErrorNote error={error} />;
  if (!data) return <><PageHeader title="Profit and Loss" right={right} /><Loading /></>;
  const tot = data.totals;
  const months = data.periods;
  const rows = [];
  for (const s of data.sections) {
    rows.push({ kind: "head", name: s.section });
    if (drill.isOpen(s.section)) {
      for (const l of s.lines) rows.push({ kind: "line", name: l.name, code: l.account_code, months: l.months, ytd: l.ytd, prior: l.prior_ytd });
    }
    rows.push({ kind: "total", name: `Total ${s.section.toLowerCase()}`, months: s.total.months, ytd: s.total.ytd, prior: s.total.prior_ytd });
    if (s.section === "Cost of sales") {
      rows.push({ kind: "result", name: "Gross profit", months: data.gross_profit.months, ytd: data.gross_profit.ytd, prior: data.gross_profit.prior_ytd });
    }
  }
  if (data.elimination.applies && data.elimination.difference) {
    rows.push({ kind: "result", name: "Net profit before the intercompany difference", months: data.net_before_difference.months,
      ytd: data.net_before_difference.ytd, prior: data.net_before_difference.prior_ytd });
    rows.push({ kind: "flag", name: "Intercompany charges that did not eliminate", months: months.map(() => null), ytd: data.elimination.difference, prior: null });
  }
  rows.push({ kind: "result", name: "Net profit", months: data.net_before_difference.months, ytd: tot.net_profit_ytd, prior: data.net_before_difference.prior_ytd, final: true });

  const money = (v) => (v == null ? "" : fmtAud(v));
  const entityName = options?.entities.find((e) => e.entity_id === entity)?.name;
  const open = (r, month, figure) => drill.show({
    statement: "pnl", entity, entityName, account: r.code, fin_year: data.fin_year, month, figure,
    name: month ? `${r.name}, ${fmtMonth(month)}` : `${r.name}, ${data.fy_label} to date`,
  });
  const nameCell = (r) => {
    if (r.kind === "head") return <SectionToggle name={r.name} open={drill.isOpen(r.name)} onToggle={() => drill.toggle(r.name)} />;
    if (r.kind !== "line") return r.name;
    return <DrillLink label={`Entries behind ${r.name}, year to date`} onClick={() => open(r, null, r.ytd)}>{r.name}</DrillLink>;
  };
  const monthCell = (r, i) => {
    if (r.kind === "head") return "";
    if (r.kind !== "line" || !r.months[i]) return money(r.months[i]);
    return <DrillLink label={`Entries behind ${r.name}, ${fmtMonth(months[i])}`} onClick={() => open(r, months[i], r.months[i])}>{money(r.months[i])}</DrillLink>;
  };
  const columns = [
    { key: "name", label: "Account", wrap: true, render: (r) => (
      <span style={{
        fontWeight: r.kind === "line" ? 450 : 700, paddingLeft: r.kind === "line" ? 12 : 0,
        color: r.kind === "flag" ? t.status.warning : r.kind === "head" ? t.accent : t.text,
        textTransform: r.kind === "head" ? "uppercase" : "none", fontSize: r.kind === "head" ? 11 : 13, letterSpacing: r.kind === "head" ? "0.06em" : 0,
      }}>{nameCell(r)}</span>
    ) },
    ...months.map((m, i) => ({ key: m, label: fmtMonth(m), align: "right", render: (r) => monthCell(r, i) })),
    { key: "ytd", label: "Year to date", align: "right", render: (r) => (r.kind === "head" ? "" : <b style={{ fontWeight: r.kind === "line" ? 500 : 750 }}>{money(r.ytd)}</b>) },
    ...(data.has_prior ? [{ key: "prior", label: "Prior year, same months", align: "right", render: (r) => (r.kind === "head" ? "" : money(r.prior)) }] : []),
  ];
  const chartRows = months.map((m, i) => {
    const sec = (n) => data.sections.find((s) => s.section === n)?.total.months[i] || 0;
    return { month: fmtMonth(m), revenue: sec("Revenue"), costs: sec("Cost of sales") + sec("Overheads"), net: data.net_before_difference.months[i] };
  });

  return (
    <>
      <PageHeader
        title="Profit and Loss"
        brief="Kill clunky software and spreadsheet chaos, and replace them with systems we own"
        subtitle={`${entityName || ""}, ${data.fy_label}, months to ${fmtDate(data.as_at)}. Every figure is a sum of general ledger lines - nothing is typed in - and the consolidated view removes charges between group entities.`}
        right={right}
      />
      <Grid cols={4} min={180}>
        <Stat label="Revenue, year to date" value={fmtAud(tot.revenue_ytd, { short: true })} emphasis
          sub={data.has_prior ? `${fmtAud(tot.prior_revenue_ytd, { short: true })} same months last year` : "No prior year in the ledger"} />
        <Stat label="Gross profit" value={fmtAud(tot.gross_profit_ytd, { short: true })} sub={`${pct(tot.gross_margin)} of revenue`} />
        <Stat label="Overheads" value={fmtAud(tot.overheads_ytd, { short: true })} />
        <Stat label="Net profit" value={fmtAud(tot.net_profit_ytd, { short: true })} tone={tot.net_profit_ytd < 0 ? "critical" : undefined}
          sub={`${pct(tot.net_margin)} net margin`} />
      </Grid>

      {data.elimination.applies && (
        <Callout tone={data.elimination.difference ? "warning" : "good"} title="Consolidation">
          {fmtAud(data.elimination.revenue)} of revenue and {fmtAud(data.elimination.costs)} of costs between group entities are removed.
          {data.elimination.difference
            ? <> They should cancel, and {fmtAud(data.elimination.difference)} does not: one entity booked a charge the other never recorded. It is shown as its own line rather than hidden. The Related Party Balance page names the entry.</>
            : " They cancel exactly."}
        </Callout>
      )}

      <SectionTitle>Statement</SectionTitle>
      <DrillBar drill={drill} note="Select a section heading to open or close it, an account for its entries this year, or a month's figure for that month." />
      <Card pad={0} rule={false}>
        <Table columns={columns} rows={rows} maxHeight={900} />
      </Card>
      <EntriesDrawer query={drill.entries} onClose={drill.close} />

      <SectionTitle>Month by month</SectionTitle>
      <Card title="Revenue, costs and net profit" hint="Costs are cost of sales plus overheads. Net profit excludes the intercompany difference, which has no month.">
        <ChartOrTable
          chart={(
            <ChartFrame height={260}>
              <ComposedChart data={chartRows} margin={{ left: 6, right: 10, top: 6 }}>
                {parts.grid}
                {parts.xAxis({ dataKey: "month" })}
                {parts.yAxis({ tickFormatter: (v) => fmtAud(v, { short: true }) })}
                {parts.tooltip({ formatter: (v) => fmtAud(v) })}
                {parts.legend()}
                <Bar dataKey="revenue" name="Revenue" fill={t.series[0]} radius={[4, 4, 0, 0]} />
                <Bar dataKey="costs" name="Costs" fill={t.series[2]} radius={[4, 4, 0, 0]} />
                <Line dataKey="net" name="Net profit" stroke={t.series[1]} strokeWidth={2} dot={{ r: 3 }} />
              </ComposedChart>
            </ChartFrame>
          )}
          table={<Table columns={[{ key: "month", label: "Month" }, { key: "revenue", label: "Revenue", align: "right", render: (r) => fmtAud(r.revenue) },
            { key: "costs", label: "Costs", align: "right", render: (r) => fmtAud(r.costs) }, { key: "net", label: "Net profit", align: "right", render: (r) => fmtAud(r.net) }]} rows={chartRows} />}
        />
      </Card>
      <p style={{ fontSize: 12, color: t.textMuted, marginTop: 14 }}>
        Not built: budgets and forecasts against actuals, accruals for work done but not yet claimed, and job-level margin.
        Each needs a source this demo does not have, and the last is better taken from the cost report than rebuilt here.
      </p>
    </>
  );
}
