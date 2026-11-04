"""Financial Planner Orchestrator Agent - coordinates portfolio analysis across specialist agents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_common import AgentInvoker, Settings, configure_bedrock_region, litellm_model_name
from agents import RunContextWrapper, function_tool
from agents.extensions.models.litellm_model import LitellmModel
from orchestration import PortfolioSummary, agent_specs, build_task, run_specialist

logger = logging.getLogger()


@dataclass
class PlannerContext:
    """Per-run context handed to the tools. The invoker is injected (real or mock)."""

    job_id: str
    invoker: AgentInvoker
    settings: Settings


@function_tool
async def invoke_reporter(wrapper: RunContextWrapper[PlannerContext]) -> str:
    """Invoke the Report Writer agent to generate portfolio analysis narrative."""
    ctx = wrapper.context
    return await run_specialist(ctx.invoker, agent_specs(ctx.settings)["reporter"], ctx.job_id)


@function_tool
async def invoke_charter(wrapper: RunContextWrapper[PlannerContext]) -> str:
    """Invoke the Chart Maker agent to create portfolio visualizations."""
    ctx = wrapper.context
    return await run_specialist(ctx.invoker, agent_specs(ctx.settings)["charter"], ctx.job_id)


@function_tool
async def invoke_retirement(wrapper: RunContextWrapper[PlannerContext]) -> str:
    """Invoke the Retirement Specialist agent for retirement projections."""
    ctx = wrapper.context
    return await run_specialist(ctx.invoker, agent_specs(ctx.settings)["retirement"], ctx.job_id)


def create_agent(
    job_id: str, summary: PortfolioSummary, invoker: AgentInvoker, settings: Settings
) -> tuple[LitellmModel, list[Any], str, PlannerContext]:
    """Create the orchestrator model, tools, task prompt and context."""
    configure_bedrock_region(settings)
    model = LitellmModel(model=litellm_model_name(settings))
    tools = [invoke_reporter, invoke_charter, invoke_retirement]
    return model, tools, build_task(job_id, summary), PlannerContext(job_id, invoker, settings)
