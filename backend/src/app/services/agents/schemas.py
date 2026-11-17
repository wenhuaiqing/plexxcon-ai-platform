"""Structured-output contracts for every agent node + LangGraph state.

Each *Result model is the return shape of one node. GraphState is the rolling
state object LangGraph threads through the graph.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.settings import settings

AgentName = Literal["data_query", "general"]


# ---------------------------------------------------------------------------
# Page context (sent from the frontend with every orb request)
# ---------------------------------------------------------------------------

class PageContext(BaseModel):
    module: str = Field(default="dashboard", max_length=64)  # the page the question was asked from
    current_item: dict[str, Any] | None = None   # the row in view, when a page passes one

    @field_validator("current_item")
    @classmethod
    def _bound_current_item(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """current_item is pasted into LLM prompts verbatim, so cap its size.
        A row is a few hundred bytes; the ceiling only bites on deliberate abuse."""
        if value is None:
            return None
        if len(value) > 64:
            raise ValueError("current_item has too many keys (max 64)")
        serialised = json.dumps(value, default=str)
        if len(serialised) > settings.orb_max_context_chars:
            raise ValueError(
                f"current_item too large ({len(serialised)} chars, max {settings.orb_max_context_chars})"
            )
        return value


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class AgentCall(BaseModel):
    """One agent call decided by the planner.

    `inputs_json` is the raw JSON string the model emits; strict structured
    output forbids an open-shape `dict[str, Any]` in a nested object, so it
    round-trips through a string and decodes via the `inputs` property.
    """
    model_config = ConfigDict(extra="forbid")

    name: AgentName
    inputs_json: str = "{}"
    reasoning: str = ""

    @property
    def inputs(self) -> dict[str, Any]:
        if not self.inputs_json:
            return {}
        try:
            value = json.loads(self.inputs_json)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


class PlannerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents_to_call: list[AgentCall]
    reasoning: str
    needs_clarification: bool = False


# ---------------------------------------------------------------------------
# Per-agent results
# ---------------------------------------------------------------------------

class DataQueryResult(BaseModel):
    """The data agent's answer, with its working shown: the query that ran, the
    rows it returned and the views it read, so every figure can be checked."""
    question: str = ""
    sql: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    interpretation: str = ""
    tables: list[str] = Field(default_factory=list)
    engine: Literal["model", "catalogue", "none"] = "model"
    answered: bool = True
    cannot_answer_reason: str = ""
    validation_passed: bool = True
    validation_errors: list[str] = Field(default_factory=list)
    repaired: bool = False


class GeneralResult(BaseModel):
    """Questions about the platform itself rather than its data."""
    model_config = ConfigDict(extra="forbid")

    answer: str
    confidence: Literal["low", "medium", "high"] = "medium"
    suggested_followups: list[str] = Field(default_factory=list)


class NodeError(BaseModel):
    node: AgentName | Literal["planner", "summariser"]
    message: str
    retry_count: int = 0


# ---------------------------------------------------------------------------
# Final LLM summarisation
# ---------------------------------------------------------------------------

class FinalMessage(BaseModel):
    message: str
    used_agents: list[AgentName] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Graph state - single source of truth threaded through every node
# ---------------------------------------------------------------------------

class GraphState(BaseModel):
    user_message: str
    page_context: PageContext = Field(default_factory=PageContext)
    planner_decision: PlannerDecision | None = None
    data_query_result: DataQueryResult | None = None
    general_result: GeneralResult | None = None
    final_message: str | None = None
    errors: list[NodeError] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
