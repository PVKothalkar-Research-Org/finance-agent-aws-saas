"""Retirement Specialist Agent Lambda Handler."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from agent_common import (
    AgentTemporaryError,
    BadRequestError,
    JobNotFoundError,
    Portfolio,
    RetryPolicy,
    UserProfile,
    classify_agent_error,
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
from observability import observe
from src import Database
from templates import RETIREMENT_INSTRUCTIONS

logger = logging.getLogger()
logger.setLevel(logging.INFO)

RETRY_POLICY = RetryPolicy().extended(RateLimitError)


def get_user_profile(db: Database, job_id: str) -> UserProfile:
    """Load the user's retirement preferences, falling back to defaults."""
    try:
        job = db.jobs.find_by_id(job_id)
        if job and job.get("clerk_user_id"):
            return UserProfile.from_row(db.users.find_by_clerk_id(job["clerk_user_id"]))
    except Exception as exc:  # noqa: BLE001 - defaults are an intentional fallback
        logger.warning("Could not load user data: %s. Using defaults.", exc)
    return UserProfile()


@with_retry(RETRY_POLICY, "Retirement", logger)
async def run_retirement_agent(job_id: str, portfolio: Portfolio, db: Database | None = None) -> dict[str, Any]:
    """Run the retirement specialist agent and persist its analysis."""
    db = db or Database()
    user = get_user_profile(db, job_id)
    model, tools, task = create_agent(job_id, portfolio, user, load_settings())

    with trace("Retirement Agent"):
        agent = Agent(name="Retirement Specialist", instructions=RETIREMENT_INSTRUCTIONS, model=model, tools=tools)
        try:
            result = await Runner.run(agent, input=task, max_turns=20)
        except RateLimitError:
            raise
        except Exception as exc:
            mapped = classify_agent_error(exc)
            if isinstance(mapped, AgentTemporaryError):
                logger.warning("Retirement temporary error: %s", exc)
                raise mapped from exc
            raise

        payload = {
            "analysis": result.final_output,
            "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "agent": "retirement",
        }
        saved = db.jobs.update_retirement(job_id, payload)
        if not saved:
            logger.error("Failed to save retirement analysis for job %s", job_id)
        return {
            "success": saved,
            "message": "Retirement analysis completed" if saved else "Analysis completed but failed to save",
            "final_output": result.final_output,
        }


def lambda_handler(event: Any, context: Any = None) -> dict[str, Any]:
    """Expects ``{"job_id": "...", "portfolio_data": {...}?}``."""
    with observe() as observability:
        try:
            logger.info("Retirement Lambda invoked with event: %s", json.dumps(event, default=str)[:500])
            if isinstance(event, str):
                event = json.loads(event)
            job_id = event.get("job_id")
            if not job_id:
                return response(400, {"error": "job_id is required"})

            db = Database()
            try:
                portfolio = resolve_portfolio(db, event, job_id)
            except JobNotFoundError:
                return response(404, {"error": f"Job {job_id} not found"})
            except BadRequestError as exc:
                return response(400, {"error": str(exc)})
            if observability and not event.get("portfolio_data"):
                observability.create_event(name="Retirement Started!", status_message="OK")

            result = asyncio.run(run_retirement_agent(job_id, portfolio, db))
            return response(200, result)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in retirement: %s", exc, exc_info=True)
            return response(500, {"success": False, "error": str(exc)})
