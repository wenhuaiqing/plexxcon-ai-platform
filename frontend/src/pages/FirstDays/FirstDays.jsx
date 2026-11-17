// The advertisement's own list, mapped to where each point is shown working,
// then the first ninety days - as a plan that starts by listening.

import { Link } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext.jsx";
import { Callout, Card, Grid, PageHeader, SectionTitle, Table } from "../../lib/ui.jsx";
import { DISCLAIMER } from "../../config.js";

const ASKED = [
  ["Turn our prototypes into rock-solid tools the whole company runs on",
   "Three workflow systems with the parts a prototype skips: write rules enforced on the server, an audit log that records refusals, schema migrations per feature, recovery from a closed tab, conflict handling, and a build that checks itself.",
   [["Bid Summary", "/bid-summary"], ["Trade Planner", "/trade-planner"], ["Material Supply Register", "/material-supply"]]],
  ["Kill clunky software and spreadsheet chaos, and replace them with systems we own",
   "Each system names the spreadsheet it replaces. The finance pages replace the month-end reconciliation spreadsheet: the related-party check finds and explains the breaks from both ledgers.",
   [["Related Party Balance", "/related-party"], ["Profit and Loss", "/profit-and-loss"], ["Balance Sheet", "/balance-sheet"]]],
  ["Connect everything: Claude, Microsoft 365/SharePoint, HubSpot, Xero",
   "The CRM sits behind one interface with a HubSpot v3 implementation (tested against a mock, not a live portal); the ledger is shaped like an accounting-system export; the model is behind the OpenAI protocol, so changing provider is configuration.",
   [["Bid Summary - CRM link", "/bid-summary?tab=form"], ["Data agent", "/data-agent"]]],
  ["Sit with estimators and site managers, spot what slows them down, and automate it",
   "The workbook stays the estimator's master: import its summary tab, paste blocks of rows, export back. The supervisor's wizard gates only what must be complete and hides modifiers until asked for.",
   [["Bid Summary", "/bid-summary"], ["Trade Planner", "/trade-planner?tab=create"]]],
  ["You've built real things with AI (agents, automations, workflows, apps) and can show us",
   "A data agent that writes checked SQL and shows its working, graded on a fixed question set including questions it must refuse; a model fallback for supplier PDFs no parser knows. The whole platform was built with Claude Code.",
   [["Data agent", "/data-agent"], ["Material Supply - PDF review", "/material-supply?job=2440&register=concrete"]]],
  ["You can code enough to wire systems together (APIs, Python/JS or similar)",
   "FastAPI and React, DuckDB, integer arithmetic so the browser preview and the server agree to the cent (proved case by case on the Library tab), deployed on Azure Container Apps from CI.",
   [["Trade Planner - parity", "/trade-planner?tab=library"]]],
  ["You can explain tech to a site manager without losing them",
   "Every page opens with what it is for in plain words, says what it does not do, and every refusal is a sentence a person can act on.",
   [["Overview", "/overview"]]],
  ["Decide what we build next",
   "The plan below starts with the people who use the prototypes, not with a technology choice.",
   []],
];

const PLAN = [
  {
    when: "Days 1-30: sit with the users",
    items: [
      "A day each with an estimator, a project manager, a site manager and admin. Watch the prototypes in use; list where people go back to a spreadsheet.",
      "Read the prototypes' code and data. Find what would lose work or let a wrong number through - that is the first fix, ahead of any feature.",
      "Agree with leadership which one prototype the business would miss most if it stopped tomorrow.",
      "Ship one small fix in week two, so the team sees things move.",
    ],
  },
  {
    when: "Days 31-60: make one of them rock-solid",
    items: [
      "Take that prototype to production: authentication through Microsoft 365, per-feature migrations, an audit log, backups, and the rules enforced on the server.",
      "Wire its first real integration - most likely HubSpot or Xero - behind an interface, so the next one is configuration rather than a rebuild.",
      "Release to a small group, fix what they find, then everyone. Measure use from the audit log, not from asking.",
    ],
  },
  {
    when: "Days 61-90: the second, and the pipeline",
    items: [
      "Start the second prototype on the same foundations; it should take half the time.",
      "Put a data agent over what is now in one place, with its questions graded, so leadership asks the data instead of asking for a report.",
      "A short, ranked list of what to build next, each with the hours it saves and who asked for it. Idea Monday, demo Tuesday, live Friday - with the controls that make Friday safe.",
    ],
  },
];

export default function FirstDays() {
  const { t } = useTheme();
  return (
    <>
      <PageHeader
        title="First 90 days"
        brief="Decide what we build next"
        subtitle="The advertisement's own list, mapped to where each point is shown working here. Then a plan for the first ninety days, which starts by sitting with the people who use the prototypes - because the right first fix is the one they need, and a demo cannot know that."
      />
      <Callout tone="neutral" title="What this is and is not">
        {DISCLAIMER} Construction is a business I know from building its data systems, but nothing here claims to know how Plexxcon works,
        what its prototypes do or which systems it runs. That is the first thing to learn.
      </Callout>
      <SectionTitle>What the role asks for, and where it is shown</SectionTitle>
      <Card pad={0} rule={false}>
        <Table maxHeight={1000} rows={ASKED} columns={[
          { key: 0, label: "From the advertisement", wrap: true, render: (r) => <i style={{ color: t.textMuted }}>"{r[0]}"</i> },
          { key: 1, label: "Here", wrap: true, render: (r) => r[1] },
          { key: 2, label: "Open", render: (r) => (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {r[2].map(([label, to]) => <Link key={to} to={to} style={{ color: t.accent, fontWeight: 650, fontSize: 12.5 }}>{label}</Link>)}
            </div>
          ) },
        ]} />
      </Card>
      <SectionTitle>The first ninety days</SectionTitle>
      <Grid cols={3} min={280}>
        {PLAN.map((p) => (
          <Card key={p.when} title={p.when}>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }}>{p.items.map((i) => <li key={i} style={{ marginBottom: 6 }}>{i}</li>)}</ul>
          </Card>
        ))}
      </Grid>
      <SectionTitle>Questions I would ask first</SectionTitle>
      <Card>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
          <li>Which prototype would hurt most if it broke on a Monday morning, and who would notice first?</li>
          <li>Where do the prototypes keep their data today, and who can change it?</li>
          <li>Which spreadsheets do people still keep beside the prototypes, and why?</li>
          <li>What is the rule on which data may go to which model?</li>
          <li>Which of HubSpot, Xero and SharePoint is the source of truth for jobs and clients?</li>
        </ul>
      </Card>
    </>
  );
}
