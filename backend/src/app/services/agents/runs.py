"""Record each assistant run: which agents, which engine, how long, whether it
worked. Never the visitor's words - the endpoint is public."""

from __future__ import annotations

import logging
from typing import Any

from src.app.services import audit, db

log = logging.getLogger(__name__)


def from_event_log(page: str | None, events: list[tuple[str, dict[str, Any]]], duration_ms: int) -> None:
    agents: list[str] = []
    errors, engine = 0, "none"
    for kind, data in events:
        if kind == "node_start" and data.get("name") not in (None, "planner", "summariser") and data["name"] not in agents:
            agents.append(data["name"])
        elif kind == "node_error":
            errors += 1
        elif kind == "node_end" and data.get("name") == "data_query":
            engine = (data.get("result") or {}).get("engine") or engine
    try:
        with db.writing() as cur:
            cur.execute("INSERT INTO agent_run VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [audit.now(), (page or "")[:40], ", ".join(agents), engine, errors == 0, errors, int(duration_ms)])
    except Exception as exc:  # noqa: BLE001 - a logging failure must not break the reply
        log.warning("agent_run not recorded (%s)", type(exc).__name__)


def summary() -> dict[str, Any]:
    row = db.rows("""SELECT count(*) AS runs, count(*) FILTER (WHERE ok) AS ok, median(duration_ms) AS median_ms,
                            count(*) FILTER (WHERE engine = 'model') AS by_model,
                            count(*) FILTER (WHERE engine = 'catalogue') AS by_catalogue FROM agent_run""")[0]
    return row
