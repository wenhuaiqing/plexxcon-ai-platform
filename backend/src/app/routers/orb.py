"""/orb/chat - runs the agent graph and streams typed events as they happen.

/orb/run-agent - the same plumbing without the planner, for buttons on a page
that already know they want the data agent and pass the row in view.

Public and rate limited (per address and overall). The operator's token is
exempt from the limit so a live demonstration is never throttled.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from src.app.services.agents.graph import build_graph
from src.app.services.rate_limit import enforce_orb_rate_limit
from src.app.services.agents.runs import from_event_log
from src.app.services.agents.runtime import set_queue
from src.app.services.agents.schemas import (
    AgentCall,
    AgentName,
    GraphState,
    PageContext,
    PlannerDecision,
)
from src.settings import settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/orb", tags=["orb"])

# Both orb routes are rate limited (per-IP + global) - see services/rate_limit.py.
_limited = [Depends(enforce_orb_rate_limit)]

END_TOTAL_TIMEOUT_SECONDS = 90.0


class OrbChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=settings.orb_max_message_chars)
    page_context: PageContext = Field(default_factory=PageContext)


class OrbRunAgentRequest(BaseModel):
    agent: AgentName
    inputs: dict[str, Any] = Field(default_factory=dict)
    # Optional user message for context in the summariser.
    message: str = Field(default="", max_length=settings.orb_max_message_chars)
    page_context: PageContext = Field(default_factory=PageContext)

    @field_validator("inputs")
    @classmethod
    def _bound_inputs(cls, value: dict[str, Any]) -> dict[str, Any]:
        serialised = json.dumps(value, default=str)
        if len(serialised) > settings.orb_max_context_chars:
            raise ValueError(f"inputs too large (max {settings.orb_max_context_chars} chars)")
        return value


def _serialise(value: Any) -> str:
    return json.dumps(value, default=_json_default)


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, tuple):
        return list(obj)
    return str(obj)


async def _run_graph_sse(initial: GraphState) -> EventSourceResponse:
    """Run the graph, drain its event queue to the client, then record the run."""
    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
    set_queue(queue)
    graph = build_graph()
    started_at = time.monotonic()

    async def runner() -> None:
        try:
            await asyncio.wait_for(graph.ainvoke(initial), timeout=END_TOTAL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            await queue.put(("node_error", {"name": "graph", "error": "total request timeout"}))
        except Exception:  # noqa: BLE001
            # Detail stays in the server log; clients get a generic message.
            log.exception("graph invocation failed")
            await queue.put(("node_error", {"name": "graph", "error": "internal error while running the agents"}))
        finally:
            await queue.put(("done", {}))

    task = asyncio.create_task(runner())

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        events: list[tuple[str, dict[str, Any]]] = []
        try:
            while True:
                event_type, data = await queue.get()
                events.append((event_type, data))
                yield {"event": event_type, "data": _serialise(data)}
                if event_type == "done":
                    break
        finally:
            if not task.done():
                task.cancel()
            page = initial.page_context.module if initial.page_context else None
            await asyncio.to_thread(from_event_log, page, events, int((time.monotonic() - started_at) * 1000))

    return EventSourceResponse(event_stream())


@router.post("/chat", dependencies=_limited)
async def chat(req: OrbChatRequest) -> EventSourceResponse:
    """Event types: planner_decision, node_start, tool_call, tool_result,
    node_end, node_error, final_message, done."""
    return await _run_graph_sse(GraphState(user_message=req.message, page_context=req.page_context))


@router.post("/run-agent", dependencies=_limited)
async def run_agent(req: OrbRunAgentRequest) -> EventSourceResponse:
    """Invoke one agent directly, skipping the planner's model call."""
    message = req.message or f"Summarise the data for the row in view on the {req.page_context.module} page."
    inputs = {"question": message, **req.inputs}
    pre_planned = PlannerDecision(
        agents_to_call=[AgentCall(name=req.agent, inputs_json=json.dumps(inputs, default=str),
                                  reasoning=f"Asked directly from {req.page_context.module}.")],
        reasoning=f"Direct call: {req.agent} from {req.page_context.module}.", needs_clarification=False)
    return await _run_graph_sse(GraphState(user_message=message, page_context=req.page_context, planner_decision=pre_planned))


@router.get("/agents")
async def list_agents() -> dict[str, list[dict[str, str]]]:
    return {"agents": [
        {"name": "data_query", "label": "Data agent", "summary": "Writes one checked SELECT over the semantic views and shows its working."},
        {"name": "general", "label": "General", "summary": "Questions about the platform itself. Never states a figure."},
    ]}
