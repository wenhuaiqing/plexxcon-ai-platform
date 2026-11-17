// Drilling on the financial statements, shared by Profit and Loss and the
// Balance Sheet.
//
//   up / down    sections collapse to their totals, or open to their accounts
//   a section    its heading toggles that section alone
//   an account   opens the ledger entries behind the figure, which add up to it
//                (the backend applies the statement's own scope, sign and
//                group eliminations, and the tests hold every figure to it)

import { useState } from "react";
import { ChevronDown, ChevronRight, ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { useTheme } from "../context/ThemeContext.jsx";
import Drawer from "../components/common/Drawer.jsx";
import { fmtAud, fmtDate, useApi } from "./api.js";
import { Button, ErrorNote, Loading, Stat, Table } from "./ui.jsx";

export function useDrill(sectionNames) {
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [open, setOpen] = useState(null);
  const all = sectionNames.length > 0 && sectionNames.every((s) => collapsed.has(s));
  return {
    collapsed,
    isOpen: (s) => !collapsed.has(s),
    toggle: (s) => setCollapsed((c) => { const n = new Set(c); if (n.has(s)) n.delete(s); else n.add(s); return n; }),
    up: () => setCollapsed(new Set(sectionNames)),
    down: () => setCollapsed(new Set()),
    canUp: !all,
    canDown: collapsed.size > 0,
    entries: open,
    show: setOpen,
    close: () => setOpen(null),
  };
}

export function DrillBar({ drill, note }) {
  const { t } = useTheme();
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", margin: "0 0 10px" }}>
      <Button icon={ChevronsDownUp} disabled={!drill.canUp} onClick={drill.up}
        title={drill.canUp ? "Collapse every section to its total" : "Already at section totals"}>Drill up</Button>
      <Button icon={ChevronsUpDown} disabled={!drill.canDown} onClick={drill.down}
        title={drill.canDown ? "Open every section to its accounts" : "Every section is open; select an account for its entries"}>Drill down</Button>
      <span style={{ fontSize: 12, color: t.textMuted }}>
        {note || "Select a section heading to open or close it, and an account for the entries behind it."}
      </span>
    </div>
  );
}

// The heading cell of a section: a toggle, so one section can be opened alone.
export function SectionToggle({ name, open, onToggle }) {
  const { t } = useTheme();
  const Icon = open ? ChevronDown : ChevronRight;
  return (
    <button type="button" onClick={onToggle} aria-expanded={open} aria-label={`${open ? "Close" : "Open"} ${name}`} style={{
      display: "inline-flex", alignItems: "center", gap: 4, border: "none", background: "none", padding: 0, cursor: "pointer",
      color: t.accent, font: "inherit", fontWeight: 700, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase",
    }}>
      <Icon size={14} />{name}
    </button>
  );
}

// An account name or a figure that opens its entries.
export function DrillLink({ children, onClick, label, strong }) {
  const { t } = useTheme();
  return (
    <button type="button" onClick={onClick} title={label} aria-label={label} style={{
      border: "none", background: "none", padding: 0, cursor: "pointer", font: "inherit", fontWeight: strong ? 700 : "inherit",
      color: "inherit", textDecoration: "underline", textDecorationColor: t.border, textUnderlineOffset: 3, textAlign: "inherit",
    }}
      onMouseEnter={(e) => { e.currentTarget.style.color = t.accent; e.currentTarget.style.textDecorationColor = t.accent; }}
      onMouseLeave={(e) => { e.currentTarget.style.color = "inherit"; e.currentTarget.style.textDecorationColor = t.border; }}>
      {children}
    </button>
  );
}

// query: { statement, entity, account, name, as_at | fin_year, month?, figure }
export function EntriesDrawer({ query, onClose }) {
  const { t } = useTheme();
  const qs = query && new URLSearchParams(Object.entries({
    statement: query.statement, entity: query.entity, account: query.account,
    as_at: query.as_at, fin_year: query.fin_year, month: query.month,
  }).filter(([, v]) => v != null && v !== "")).toString();
  const { data, error } = useApi(query ? `/api/finance/entries?${qs}` : null);
  const bs = query?.statement === "bs";
  const group = query?.entity === "GROUP";
  const ties = data && query && Math.abs(data.closing - query.figure) < 0.005;
  const cols = [
    { key: "date", label: "Date", render: (r) => fmtDate(r.date) },
    ...(group ? [{ key: "entity_id", label: "Entity" }] : []),
    { key: "description", label: "Entry", wrap: true, render: (r) => (
      <span>{r.description}<span style={{ color: t.textMuted, fontSize: 11 }}> {r.journal_id}{r.project_id ? `, job ${r.project_id}` : ""}{r.counterparty_id ? `, with ${r.counterparty_id}` : ""}</span></span>
    ) },
    { key: "amount", label: "Amount", align: "right", render: (r) => fmtAud(r.amount, { decimals: 2 }) },
    ...(bs ? [{ key: "balance", label: "Balance", align: "right", render: (r) => fmtAud(r.balance, { decimals: 2 }) }] : []),
  ];
  const period = data && `${fmtDate(data.from)} to ${fmtDate(data.to)}`;
  return (
    <Drawer open={Boolean(query)} onClose={onClose} width={720} title={query ? `${query.name}: entries` : ""}
      subtitle={data ? `${query.entityName}, ${period}. ${bs
        ? "Opening balance at the start of the financial year, then every entry since."
        : "Every entry in the period."}${data.eliminated ? " Entries with other group entities are left out, as they are on the consolidated statement." : ""}` : ""}>
      {error && <ErrorNote error={error} />}
      {!data && !error && <Loading />}
      {data && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: `repeat(${bs ? 3 : 2}, minmax(0, 1fr))`, gap: 10, marginBottom: 12 }}>
            {bs && <Stat label={`Opening, ${fmtDate(data.from)}`} value={fmtAud(data.opening)} />}
            <Stat label={`Movement, ${data.count} entries`} value={fmtAud(data.movement, { signed: bs })} />
            <Stat label={bs ? `Closing, ${fmtDate(data.to)}` : "Total"} value={fmtAud(data.closing)} emphasis
              tone={ties ? "good" : "critical"} sub={ties ? "Agrees with the statement" : `Statement shows ${fmtAud(query.figure)}`} />
          </div>
          <Table columns={cols} rows={data.lines} maxHeight={560} empty="No entries in the period." />
        </>
      )}
    </Drawer>
  );
}
