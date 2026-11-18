// Auto-discovers pages under src/pages/<Section>/<Page>.jsx. The folder name
// becomes the URL slug; MODULE_META fixes the label, icon, group and order.

import {
  Bot, ClipboardList, Compass, HardHat, Landmark, Milestone, Network, Scale, TrendingUp, Truck,
} from "lucide-react";

const PAGE_MODULES = import.meta.glob("./pages/*/*.jsx", { eager: true });

export const MODULE_META = {
  Overview:       { label: "Overview",                 icon: Compass,       group: "Start here", order: 0 },
  BidSummary:     { label: "Bid Summary",              icon: ClipboardList, group: "Workflow systems", order: 1, slug: "bid-summary" },
  TradePlanner:   { label: "Trade Planner",            icon: HardHat,       group: "Workflow systems", order: 2, slug: "trade-planner" },
  MaterialSupply: { label: "Material Supply Register", icon: Truck,         group: "Workflow systems", order: 3, slug: "material-supply" },
  ProfitAndLoss:  { label: "Profit and Loss",          icon: TrendingUp,    group: "Finance reports", order: 4, slug: "profit-and-loss" },
  BalanceSheet:   { label: "Balance Sheet",            icon: Scale,         group: "Finance reports", order: 5, slug: "balance-sheet" },
  RelatedParty:   { label: "Related Party Balance",    icon: Network,       group: "Finance reports", order: 6, slug: "related-party" },
  DataAgent:      { label: "Data agent",               icon: Bot,           group: "AI", order: 7, slug: "data-agent" },
  FirstDays:      { label: "First 90 days",            icon: Milestone,     group: "The role", order: 8, slug: "first-90-days" },
};

export function getRoutes() {
  const seen = new Map();
  for (const [path, module] of Object.entries(PAGE_MODULES)) {
    const match = path.match(/^\.\/pages\/([^/]+)\/([^/]+)\.jsx$/);
    if (!match || seen.has(match[1]) || !MODULE_META[match[1]]) continue;
    const meta = MODULE_META[match[1]];
    seen.set(match[1], { section: match[1], label: meta.label, icon: meta.icon, group: meta.group, order: meta.order,
      to: `/${meta.slug || match[1].toLowerCase()}`, component: module.default });
  }
  return [...seen.values()].sort((a, b) => a.order - b.order);
}

export const FINANCE_ICON = Landmark;

// A line under a sidebar heading, where the heading alone undersells the group.
export const GROUP_NOTES = {
  "Workflow systems": "Where the work is done. The kind of systems I build and run in production, written from scratch here.",
  "Finance reports": "The kind of reports I build and run in production, written from scratch here.",
};
