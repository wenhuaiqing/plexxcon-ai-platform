# plexxcon-ai-platform

Portfolio demo: an operations platform for a builder - three workflow systems
(Bid Summary, Trade Planner, Material Supply Register), finance reporting
(Profit and Loss, Balance Sheet, Related Party Balance) over a synthetic
ledger, and a data agent that answers questions about all of it with checked
SQL and shows its working. Built for an application to Plexxcon (AI Lead) and
named for it. **Not affiliated with or endorsed by Plexxcon. All data is synthetic.**

The agent layer (planner -> agents -> summariser on LangGraph, streamed to the
assistant panel over SSE, the SQL gate, the rate limiter, the OpenAI-protocol
client) comes from github.com/wenhuaiqing/ai-powered-app; the frame (DuckDB
working copy, governed writes, build manifest, Terraform, CI) from the
author's earlier demos.

## Layout

```
plexxcon-ai-platform/
├── backend/           FastAPI + Python 3.12 (uv)
│   └── src/app/
│       ├── calc/        integer arithmetic: money, bid totals, trade planning
│       ├── migrations/  one folder per feature, numbered, checksummed
│       ├── pipeline/    reference (every assumption and seeded defect), generate,
│       │                migrate, acceptance
│       ├── services/    finance, bids, trades, msr, msr_recon, supplier_docs, crm,
│       │                catalogue, agents/ (planner, data_query, general, summariser),
│       │                llm, sql_validator, audit, auth, rate_limit, db
│       └── routers/     platform, finance, bids, trades, msr, orb (SSE)
├── scripts/           build_platform.py - everything from nothing
├── evals/             run_agent_eval.py -> status.json (shown on the Data agent page)
├── frontend/          React 18 + Vite; pages/<Section>/<Page>.jsx auto-discovered
└── infra-azure/       Terraform; build.sha256 is the pinned manifest
```

## How to run

```bash
cd backend && uv sync && uv run python ../scripts/build_platform.py && uv run uvicorn src.main:app --port 8061
cd frontend && npm install && npm run dev     # :5261
```

Tests: `cd backend && uv run pytest`. Pages: `cd frontend && node evals/check-pages.mjs`.
Operator path: `TOKEN=<DEMO_WRITE_TOKEN> node evals/flow.mjs`.

## Conventions

- **No emojis in code or output.** Australian English; dates DD/MM/YYYY on screen;
  straight quotes and hyphens only (the page check fails on typographic ones).
- **Personal identity only.** Commits, CI, registry, README and infrastructure use
  the author's personal accounts. No employer name, work e-mail, work machine path,
  internal system, or real data from any employer appears in this repository.
- Money and quantities are integers (cents, hundredths, basis points). No float
  decides a figure. The browser's calculators (`frontend/src/lib/*Calc.js`) mirror
  `backend/src/app/calc/` and the Trade Planner's Library tab proves they agree.
- Every defect the generator seeds is declared once in `pipeline/reference.py`;
  tests assert each is found from the data, never from the reference.
- A feature owns its schema: add a numbered file to `migrations/<feature>/`, never
  edit one that has run (the runner checks checksums).
- Every write goes through `auth.require_write` (open to visitors under a rate
  limit while PUBLIC_WRITES is on; reset always needs the token), is audit-logged,
  and is refused - not warned - when the rule says no. Nobody decides their own request. Nothing a parser reads is
  recorded until a person confirms it. Deletes in the register are soft.
- The data agent reads only the `v_*` views (migrations/agent), through the SQL
  gate, on a connection with external access off. It cannot write. Numbers on
  screen come from the data.
- Changing the generator, a migration or the calculations changes the output:
  rebuild with `--write-manifest` and commit `infra-azure/build.sha256`, or CI
  and the image build fail.
- Azure: one resource group, scale to zero, no registry, no vault, no database.
  Do not add a resource that costs money at rest.
- Named for the business it was built for, and says so: the not-affiliated line
  stays in the sidebar, the First 90 days page and the README. It uses Plexxcon's
  public logo, favicon and colours (teal #4AB7C3 on black, from plexxcon.com.au),
  so that line must never be removed or made less visible. Nothing claims to know
  how they operate.
