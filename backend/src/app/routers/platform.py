"""What the deployment is, the overview's counts, the data agent's page, and reset."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.app.pipeline import acceptance, migrate
from src.app.pipeline import reference as ref
from src.app.services import audit, catalogue, db, llm, sql_validator
from src.app.services.agents import runs
from src.app.services.auth import actor, require_write_token
from src.settings import REPO_ROOT, settings

router = APIRouter(prefix="/api", tags=["platform"])
STARTED = time.time()
EVAL_STATUS = REPO_ROOT / "evals" / "status.json"


class Sql(BaseModel):
    sql: str = Field(max_length=2000)


@router.get("/meta")
def meta() -> dict:
    return {
        "version": settings.git_sha or "dev", "uptime_seconds": int(time.time() - STARTED), "synthetic_data": True,
        "today": ref.DEMO_TODAY.isoformat(), "ledger_to": ref.LEDGER_END.isoformat(),
        "llm_configured": llm.configured(), "llm_model": settings.llm_chat_model if llm.configured() else None,
        "writes_enabled": settings.public_writes or bool(settings.demo_write_token), "writes_public": settings.public_writes, "build_seconds": db.scalar("SELECT v FROM kv WHERE k = 'build_seconds'"),
        "people": ref.PEOPLE,
    }


@router.get("/overview")
def overview() -> dict:
    one = lambda sql: db.scalar(sql)  # noqa: E731
    return {
        "bids": {"tenders": one("SELECT count(*) FROM bid"), "revisions": one("SELECT count(*) FROM bid_revision"),
                 "drafts": one("SELECT count(*) FROM bid_draft"),
                 "open_value": one("SELECT sum(amount_cents) / 100.0 FROM crm_deal WHERE dealstage IN ('qualifying', 'tendering', 'submitted')")},
        "trades": {"requests": one("SELECT count(*) FROM tp_request WHERE status <> 'draft'"),
                   "awaiting": one("SELECT count(*) FROM tp_request WHERE status IN ('pending', 'tentative')"),
                   "rates": one("SELECT count(*) FROM tp_rate"),
                   "approved_hours": one("SELECT sum(total_hours_x100) / 100.0 FROM tp_request WHERE status = 'accepted'")},
        "msr": {"jobs": one("SELECT count(*) FROM msr_enrolment"), "dockets": one("SELECT count(*) FROM msr_docket WHERE deleted_at IS NULL"),
                "invoices": one("SELECT count(*) FROM msr_invoice WHERE deleted_at IS NULL"),
                "not_green": one("SELECT count(*) FROM msr_invoice WHERE deleted_at IS NULL AND recon_status <> 'green'"),
                "inbox": one("SELECT count(*) FROM msr_document WHERE status = 'inbox'")},
        "finance": {"ledger_lines": one("SELECT count(*) FROM gl_line"), "entities": one("SELECT count(*) FROM entity WHERE is_group"),
                    "months": one("SELECT count(DISTINCT last_day(posting_date)) FROM gl_line")},
        "audit": {"entries": one("SELECT count(*) FROM audit_log"), "refused": one("SELECT count(*) FROM audit_log WHERE outcome = 'refused'")},
        "migrations": db.rows("SELECT feature, count(*) AS files FROM schema_migrations GROUP BY 1 ORDER BY 1"),
        "acceptance": [name for name, _ in acceptance.CHECKS],
        "features": migrate.FEATURES,
    }


@router.get("/audit")
def audit_all(system: str | None = None) -> list[dict]:
    where, params = ("WHERE system = ?", [system]) if system else ("", [])
    return db.rows(f"""SELECT ts, actor, system, project_id, subject, action, outcome, detail, reason FROM audit_log
                       {where} ORDER BY audit_id DESC LIMIT 200""", params)


@router.get("/agent")
def agent() -> dict:
    status = json.loads(EVAL_STATUS.read_text(encoding="utf-8")) if EVAL_STATUS.exists() else None
    return {
        "configured": llm.configured(), "model": settings.llm_chat_model if llm.configured() else None,
        "fallback_model": settings.llm_fallback_model or None,
        "views": catalogue.schema(), "rules": catalogue.RULES,
        "known": [{"question": q, "sql": sql} for q, sql, _ in catalogue.KNOWN],
        "gate": {"allowed_views": sorted(sql_validator.ALLOWED_TABLES), "forbidden_keywords": sorted(sql_validator.FORBIDDEN_KEYWORDS),
                 "forbidden_functions": sorted(sql_validator.FORBIDDEN_FUNCTIONS),
                 "default_limit": sql_validator.DEFAULT_LIMIT, "max_limit": sql_validator.MAX_LIMIT},
        "eval": status, "runs": runs.summary(),
    }


@router.post("/agent/gate")
def gate(body: Sql) -> dict:
    """Put any SQL to the gate and see what it says. Runs nothing."""
    outcome = sql_validator.validate(body.sql)
    return {"ok": outcome.ok, "errors": outcome.errors, "sql": outcome.sql if outcome.ok else None,
            "tables": outcome.tables_referenced}


@router.post("/reset", dependencies=[Depends(require_write_token)])
def reset(request: Request) -> dict:
    """Back to the built state: every draft, decision and confirmed docket made in the demo is discarded."""
    db.reset_to_build()
    with db.writing() as cur:
        audit.record(cur, actor(request), "platform", "demo", "reset to built state")
    return {"reset": True}
