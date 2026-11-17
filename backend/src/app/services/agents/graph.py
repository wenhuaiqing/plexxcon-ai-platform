"""LangGraph topology: planner -> agents_runner -> summariser.

The agents run in one sequential node iterating the planner's list. Every node
has a time budget and a deterministic way to fail: an error is recorded on the
state and streamed to the page, and the run carries on to an honest summary.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any, Awaitable, Callable

from langgraph.graph import END, START, StateGraph

from src.app.services.agents.nodes import data_query, general
from src.app.services.agents.planner import plan
from src.app.services.agents.runtime import emit
from src.app.services.agents.schemas import (
    AgentName,
    GraphState,
    NodeError,
)
from src.app.services.agents.summariser import summarise

log = logging.getLogger(__name__)

PER_NODE_TIMEOUT_SECONDS = 30.0


def public_error(exc: BaseException, node: str) -> str:
    """Client-safe error text. Raw exception strings can carry provider
    responses, file paths or generated SQL, so only the timeout case is
    described specifically; everything else is logged server-side."""
    if isinstance(exc, asyncio.TimeoutError):
        return f"{node} timed out after {int(PER_NODE_TIMEOUT_SECONDS)}s"
    return f"{node} failed ({type(exc).__name__})"

NODE_RUNNERS: dict[AgentName, Callable[[GraphState, dict[str, Any]], Awaitable[Any]]] = {
    "data_query": data_query.run,
    "general": general.run,
}

# Map an agent name to the GraphState field that holds its result.
RESULT_FIELDS: dict[AgentName, str] = {
    "data_query": "data_query_result",
    "general": "general_result",
}


async def _planner_node(state: GraphState) -> dict[str, Any]:
    # /orb/run-agent pre-populates planner_decision to invoke a specific
    # agent directly. In that case we skip the LLM call but still emit the
    # same event sequence so the frontend trace renders identically.
    if state.planner_decision is not None:
        await emit("node_start", {"name": "planner"})
        await emit("planner_decision", state.planner_decision.model_dump())
        await emit("node_end", {"name": "planner", "result": state.planner_decision.model_dump()})
        return {}

    await emit("node_start", {"name": "planner"})
    try:
        decision = await asyncio.wait_for(plan(state), timeout=PER_NODE_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        log.exception("planner node failed")
        msg = public_error(exc, "planner")
        await emit("node_error", {"name": "planner", "error": msg})
        return {"errors": state.errors + [NodeError(node="planner", message=msg)]}

    await emit("planner_decision", decision.model_dump())
    await emit("node_end", {"name": "planner", "result": decision.model_dump()})
    return {"planner_decision": decision}


async def _agents_runner_node(state: GraphState) -> dict[str, Any]:
    if state.planner_decision is None:
        return {}

    updates: dict[str, Any] = {}
    errors = list(state.errors)
    for call in state.planner_decision.agents_to_call:
        if call.name not in NODE_RUNNERS:
            await emit("node_error", {"name": call.name, "error": "unknown agent"})
            errors.append(NodeError(node=call.name, message="unknown agent"))
            continue

        await emit("node_start", {"name": call.name, "inputs": call.inputs})
        try:
            result = await asyncio.wait_for(
                NODE_RUNNERS[call.name](state, call.inputs),
                timeout=PER_NODE_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("agent node %s failed", call.name)
            msg = public_error(exc, call.name)
            await emit("node_error", {"name": call.name, "error": msg})
            errors.append(NodeError(node=call.name, message=msg))
            continue

        field = RESULT_FIELDS[call.name]
        updates[field] = result
        await emit("node_end", {"name": call.name, "result": result.model_dump()})

    updates["errors"] = errors
    return updates


async def _summariser_node(state: GraphState) -> dict[str, Any]:
    await emit("node_start", {"name": "summariser"})
    try:
        final = await asyncio.wait_for(summarise(state), timeout=PER_NODE_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        log.exception("summariser failed")
        msg = public_error(exc, "summariser")
        await emit("node_error", {"name": "summariser", "error": msg})
        message = "Sorry, I ran into a problem composing the final answer."
        await emit("final_message", {"message": message, "used_agents": []})
        return {
            "final_message": message,
            "errors": state.errors + [NodeError(node="summariser", message=msg)],
        }

    await emit("final_message", final.model_dump())
    await emit("node_end", {"name": "summariser", "result": final.model_dump()})
    return {"final_message": final.message}


@lru_cache(maxsize=1)
def build_graph():
    """Compile the LangGraph once per process."""
    g = StateGraph(GraphState)
    g.add_node("planner", _planner_node)
    g.add_node("agents_runner", _agents_runner_node)
    g.add_node("summariser", _summariser_node)
    g.add_edge(START, "planner")
    g.add_edge("planner", "agents_runner")
    g.add_edge("agents_runner", "summariser")
    g.add_edge("summariser", END)
    return g.compile()
