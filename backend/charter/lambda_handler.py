"""Chart Maker Agent Lambda Handler."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from agent_common import (
    BadRequestError,
    JobNotFoundError,
    Portfolio,
    RetryPolicy,
    load_settings,
    resolve_portfolio,
    response,
    with_retry,
)
from agents import Agent, Runner, trace
from litellm.exceptions import RateLimitError

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

from agent import create_agent
from analysis import extract_charts
from observability import observe
from src import Database
from templates import CHARTER_INSTRUCTIONS

logger = logging.getLogger()
logger.setLevel(logging.INFO)

RETRY_POLICY = RetryPolicy(retryable=(RateLimitError,))


@with_retry(RETRY_POLICY, "Charter", logger)
async def run_charter_agent(job_id: str, portfolio: Portfolio, db: Database | None = None) -> dict[str, Any]:
    """Run the charter agent, parse its JSON output and save the charts."""
    model, task = create_agent(job_id, portfolio, load_settings())

    with trace("Charter Agent"):
        agent = Agent(name="Chart Maker", instructions=CHARTER_INSTRUCTIONS, model=model)
        result = await Runner.run(agent, input=task, max_turns=5)

        output = result.final_output
        logger.info("Charter: Agent completed, output length: %d", len(output) if output else 0)
        if output:
            logger.info("Charter: Output preview (first 1000 chars): %s", output[:1000])
        else:
            logger.warning("Charter: Agent returned empty output!")

        charts = extract_charts(output)
        saved = False
        if db and charts:
            try:
                saved = bool(db.jobs.update_charts(job_id, charts))
                logger.info("Charter: Database update returned: %s", saved)
            except Exception as exc:  # noqa: BLE001
                logger.error("Charter: Database error: %s", exc)

        return {
            "success": saved,
            "message": f"Generated {len(charts)} charts" if saved else "Failed to generate charts",
            "charts_generated": len(charts),
            "chart_keys": list(charts),
        }


def lambda_handler(event: Any, context: Any = None) -> dict[str, Any]:
    """Expects ``{"job_id": "...", "portfolio_data": {...}?}``."""
    with observe():
        try:
            if isinstance(event, str):
                event = json.loads(event)
            job_id = event.get("job_id")
            if not job_id:
                return response(400, {"error": "job_id is required"})

            db = Database()
            try:
                portfolio = resolve_portfolio(db, event, job_id)
            except JobNotFoundError:
                return response(404, {"error": "Job not found"})
            except BadRequestError as exc:
                return response(400, {"error": str(exc)})

            logger.info("Charter: Processing job %s", job_id)
            result = asyncio.run(run_charter_agent(job_id, portfolio, db))
            return response(200, result)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in charter: %s", exc, exc_info=True)
            return response(500, {"success": False, "error": str(exc)})
