// Balance Sheet: by entity or consolidated, at any month end, against the last year end.

import { useState } from "react";
import { Link } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext.jsx";
import { fmtAud, fmtDate, useApi } from "../../lib/api.js";
import { Badge, Callout, Card, ErrorNote, Grid, Loading, PageHeader, Select, Stat, Table } from "../../lib/ui.jsx";
import { EntityPicker } from "../ProfitAndLoss/ProfitAndLoss.jsx";
import { DrillBar, DrillLink, EntriesDrawer, SectionToggle, useDrill } from "../../lib/statement.jsx";

const SECTIONS = ["Current assets", "Non-current assets", "Current liabilities", "Non-current liabilities", "Equity"];

// Lines the statement calculates rather than posts: where each is explained instead.
const DERIVED = {
  "Retained earnings": { to: "/profit-and-loss", text: "Earnings of earlier years, from Profit and Loss" },
  "Current year earnings": { to: "/profit-and-loss", text: "This year's net profit, on Profit and Loss" },
  "Unreconciled intercompany balances": { to: "/related-party", text: "Explained on Related Party Balance" },
};

export default function BalanceSheet() {
  const { t } = useTheme();
  const { data: options } = useApi("/api/finance/options");
  const [entity, setEntity] = useState("GROUP");
  const [asAt, setAsAt] = useState("");
  const { data, error } = useApi(`/api/finance/balance-sheet?entity=${entity}${asAt ? `&as_at=${asAt}` : ""}`);
  const drill = useDrill(SECTIONS);

  const right = options && (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      <EntityPicker options={options} value={entity} onChange={setEntity} />
      <Select label="As at" value={asAt || options.latest} onChange={setAsAt} options={options.month_ends.map((m) => ({ value: m, label: fmtDate(m) }))} />
    </div>
  );
  if (error) return <ErrorNote error={error} />;
  if (!data) return <><PageHeader title="Balance Sheet" right={right} /><Loading /></>;
  const tot = data.totals;
  const compare = Boolean(data.compare_as_at);

  const rows = [];
  const add = (section) => {
    const s = data.sections.find((x) => x.section === section);
    rows.push({ kind: "head", name: section });
    if (drill.isOpen(section)) {
      for (const l of s.lines) rows.push({ kind: l.flag ? "flag" : "line", name: l.name, code: l.account_code, now: l.balance, then: l.prior });
    }
    rows.push({ kind: "total", name: `Total ${section.toLowerCase()}`, now: s.total, then: s.prior_total });
  };
  add("Current assets");
  add("Non-current assets");
  rows.push({ kind: "result", name: "Total assets", now: tot.assets, then: tot.prior_assets });
  add("Current liabilities");
  add("Non-current liabilities");
  rows.push({ kind: "result", name: "Total liabilities", now: tot.liabilities, then: tot.prior_liabilities });
  rows.push({ kind: "result", name: "Net assets", now: tot.net_assets, then: tot.prior_net_assets });
  add("Equity");

  const entityName = options?.entities.find((e) => e.entity_id === entity)?.name;
  const nameCell = (r) => {
    if (r.kind === "head") return <SectionToggle name={r.name} open={drill.isOpen(r.name)} onToggle={() => drill.toggle(r.name)} />;
    if (r.kind !== "line" && r.kind !== "flag") return r.name;
    const derived = DERIVED[r.name];
    if (derived) {
      return <>{r.name} <Link to={derived.to} style={{ fontSize: 11, fontWeight: 500, color: t.textMuted, marginLeft: 4 }}>{derived.text}</Link></>;
    }
    return (
      <DrillLink label={`Entries behind ${r.name}`} onClick={() => drill.show({
        statement: "bs", entity, entityName, account: r.code, name: r.name, as_at: data.as_at, figure: r.now,
      })}>{r.name}</DrillLink>
    );
  };
  const columns = [
    { key: "name", label: "", wrap: true, render: (r) => (
      <span style={{
        fontWeight: r.kind === "line" ? 450 : 700, paddingLeft: r.kind === "line" || r.kind === "flag" ? 12 : 0,
        color: r.kind === "flag" ? t.status.warning : r.kind === "head" ? t.accent : t.text,
        textTransform: r.kind === "head" ? "uppercase" : "none", fontSize: r.kind === "head" ? 11 : 13, letterSpacing: r.kind === "head" ? "0.06em" : 0,
      }}>{nameCell(r)}</span>
    ) },
    { key: "now", label: fmtDate(data.as_at), align: "right", render: (r) => (r.kind === "head" ? "" : <span style={{ fontWeight: r.kind === "line" ? 450 : 700 }}>{fmtAud(r.now)}</span>) },
    ...(compare ? [
      { key: "then", label: fmtDate(data.compare_as_at), align: "right", render: (r) => (r.kind === "head" || r.then == null ? "" : fmtAud(r.then)) },
      { key: "move", label: "Movement", align: "right", render: (r) => (r.kind === "head" || r.then == null ? "" : fmtAud(r.now - r.then, { signed: true })) },
    ] : []),
  ];
  return (
    <>
      <PageHeader
        title="Balance Sheet"
        brief="Kill clunky software and spreadsheet chaos, and replace them with systems we own"
        subtitle={`At ${fmtDate(data.as_at)}${compare ? `, against the year end ${fmtDate(data.compare_as_at)}` : ""}. Retained earnings and current-year earnings are calculated from the ledger, so the statement balances by construction - and the check below says so rather than assuming it.`}
        right={right}
      />
      <Grid cols={4} min={180}>
        <Stat label="Net assets" value={fmtAud(tot.net_assets, { short: true })} emphasis
          sub={compare ? `${fmtAud(tot.net_assets - tot.prior_net_assets, { short: true, signed: true })} since the year end` : undefined} />
        <Stat label="Cash at bank" value={fmtAud(tot.cash, { short: true })} />
        <Stat label="Working capital" value={fmtAud(tot.working_capital, { short: true })} sub={tot.current_ratio != null ? `Current ratio ${tot.current_ratio.toFixed(2)}` : undefined} />
        <Stat label="Assets = liabilities + equity" value={data.balances ? "Balances" : "Out"} tone={data.balances ? "good" : "critical"}
          sub={`Difference ${fmtAud(tot.difference)}`} />
      </Grid>
      {entity === "GROUP" && tot.unreconciled_intercompany !== 0 && (
        <Callout tone="warning" title="Intercompany balances that did not eliminate">
          Balances between group entities are removed on consolidation. {fmtAud(Math.abs(tot.unreconciled_intercompany))} is left, because the two
          sides of some balances disagree. It is carried as its own line in current assets so the group still balances, and the
          Related Party Balance page shows which entries cause it.
        </Callout>
      )}
      <div style={{ marginTop: 14 }}><DrillBar drill={drill} /></div>
      <Card pad={0} rule={false}>
        <Table columns={columns} rows={rows} maxHeight={1100} />
      </Card>
      <EntriesDrawer query={drill.entries} onClose={drill.close} />
      <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Badge tone="neutral">Sign convention: assets and liabilities both shown positive</Badge>
        <Badge tone="neutral">Financial year 1 July to 30 June</Badge>
      </div>
    </>
  );
}
