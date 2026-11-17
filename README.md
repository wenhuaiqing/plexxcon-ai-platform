# Plexxcon AI operations platform (demo)

> Built for a job application. **Not affiliated with or endorsed by Plexxcon.**
> All data - jobs, clients, suppliers, ledgers, people - is synthetic. The logo,
> favicon and colours are Plexxcon's own public ones, used to show the work in
> their context.

An operations platform for a builder: three workflow systems, finance reporting
over the same data, and a data agent that answers questions about all of it and
shows its working.

| | What it does | What it replaces |
|---|---|---|
| **Bid Summary** | The one-page commercial summary of a tender. Every price change is an immutable, numbered revision. CRM link (HubSpot-shaped), workbook import and export-back, PDF, two-tier validation, shared drafts with presence and explicit conflict resolution. | A summary spreadsheet emailed around as "v3 final". |
| **Trade Planner** | A wizard for a trades and labour request: tasks draw production rates from one shared library, locations generate cost codes, working days (QLD holidays skipped) give a finish date, overtime is split. A second person accepts or rejects, with mandatory feedback. | A labour spreadsheet per job and approval by email. |
| **Material Supply Register** | Concrete (m3) and reinforcement (t) per job: locked budget, live forecast with a reason for every change and a measure tool, pours and dockets, supplier invoices reconciled line by line - green, amber, red. Supplier PDFs read by a parser per supplier, a model as the fallback, confirmed by a person. | A supply spreadsheet per project. |
| **Finance** | Profit and Loss, Balance Sheet and Related Party Balance from a four-entity ledger, consolidated with eliminations. The related-party check finds and explains each intercompany break from both ledgers. | The month-end reconciliation spreadsheet. |
| **Data agent** | Plain-English questions; one SQL query over semantic views, through a gate, read-only; the answer carries its query and rows. Graded against hand-written reference answers, including questions it must refuse. | Asking someone for a report. |

## How it is built

- **Backend**: FastAPI, Python 3.12, DuckDB. Integer arithmetic throughout, so
  the browser preview and the server agree to the cent.
- **Agent layer**: from [ai-powered-app](https://github.com/wenhuaiqing/ai-powered-app):
  a LangGraph planner -> agents -> summariser, streamed over SSE, behind the
  OpenAI protocol (Gemini on this deployment; any provider by configuration).
- **Frontend**: React 18 + Vite, Recharts.
- **Data**: generated from a seed at image build, with defects seeded on purpose
  (`backend/src/app/pipeline/reference.py`). The build applies each feature's
  migrations, runs acceptance checks and verifies every table against
  `infra-azure/build.sha256` - an image that cannot reproduce the pinned output
  is never published.
- **Azure**: one Container App (nginx + FastAPI sidecar), consumption plan,
  scale to zero, public images on GHCR, a A$3 budget tripwire. Nothing costs
  money at rest.

## Run it

```bash
cd backend && uv sync && uv run python ../scripts/build_platform.py && uv run uvicorn src.main:app --port 8061
cd frontend && npm install && npm run dev        # http://localhost:5261
```

`cd backend && uv run pytest` for the tests; `node frontend/evals/check-pages.mjs`
renders every page on desktop and phone; `TOKEN=... node frontend/evals/flow.mjs`
drives the write path. `uv run python ../evals/run_agent_eval.py` grades the
agent (needs a model key in `.env`).

The public link is an open demo: any visitor can use the three workflow
systems, acting as any of the demo people, under a per-address write limit.
The rules still refuse - nobody approves their own request - and every refusal
is audit-logged. Changes live in a working copy that returns to the build on
every cold start. Resetting on demand needs the operator's token
(`?write_token=...`), which is never published. `PUBLIC_WRITES=false` on the
server and `VITE_PUBLIC_WRITES=false` at build restore the token gate on every write.
