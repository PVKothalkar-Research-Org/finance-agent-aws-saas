"""Chart Maker Agent - builds the model and prompt for chart generation."""

from __future__ import annotations

import logging

from agent_common import Portfolio, Settings, configure_bedrock_region, litellm_model_name
from agents.extensions.models.litellm_model import LitellmModel
from analysis import analyze_portfolio
from templates import create_charter_task

logger = logging.getLogger()


def create_agent(job_id: str, portfolio: Portfolio, settings: Settings) -> tuple[LitellmModel, str]:
    """Create the charter model and task (no tools: the agent returns JSON directly)."""
    configure_bedrock_region(settings)
    logger.info("Charter: Creating agent with model_id=%s, region=%s", settings.bedrock_model_id, settings.bedrock_region)
    logger.info("Charter: Job ID: %s", job_id)
    model = LitellmModel(model=litellm_model_name(settings))
    analysis = analyze_portfolio(portfolio)
    task = create_charter_task(analysis)
    logger.info("Charter: Task created, length: %d characters", len(task))
    return model, task
