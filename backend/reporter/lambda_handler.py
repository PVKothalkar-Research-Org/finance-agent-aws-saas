"""Report Writer Agent Lambda Handler."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from agent_common import (
    BadRequestError,
    JobNotFoundError,
    Portfolio,
    RetryPolicy,
    UserProfile,
    load_settings,
    resolve_portfolio,
    response,
    with_retry,
)
from agents import Agent, Runner, trace
from judge import evaluate
from litellm.exceptions import RateLimitError

GUARD_AGAINST_SCORE = 0.3  # Guard against score being too low
FALLBACK_REPORT = "I'm sorry, I'm not able to generate a report for you. Please try again later."

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

from agent import ReporterContext, create_agent
from observability import observe
from src import Database
from templates import REPORTER_INSTRUCTIONS

logger = logging.getLogger()
logger.setLevel(logging.INFO)

RETRY_POLICY = RetryPolicy(retryable=(RateLimitError,))


def apply_judge_guard(report: str, score: float) -> str:
    """Replace a report whose judge score is below the guard threshold."""
    if score < GUARD_AGAINST_SCORE:
        logger.error("Reporter score is too low: %s", score)
        return FALLBACK_REPORT
    return report


@with_retry(RETRY_POLICY, "Reporter", logger)
async def run_reporter_agent(
    job_id: str,
    portfolio: Portfolio,
    user: UserProfile,
    db: Database,
    observability: Any = None,
) -> dict[str, Any]:
    """Run the reporter agent, optionally judge the result, and save the report."""
    model, tools, task, context = create_agent(job_id, portfolio, user, load_settings(), db)

    with trace("Reporter Agent"):
        agent = Agent[ReporterContext](
            name="Report Writer", instructions=REPORTER_INSTRUCTIONS, model=model, tools=tools
        )
        result = await Runner.run(agent, input=task, context=context, max_turns=10)
        report = result.final_output

        if observability:
            with observability.start_as_current_span(name="judge") as span:
                evaluation = await evaluate(REPORTER_INSTRUCTIONS, task, report)
                score = evaluation.score / 100
                span.score(name="Judge", value=score, data_type="NUMERIC", comment=evaluation.feedback)
                observability.create_event(
                    name="Judge Event", status_message=f"Score: {score} - Feedback: {evaluation.feedback}"
                )
                report = apply_judge_guard(report, score)

        payload = {
            "content": report,
            "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "agent": "reporter",
        }
        saved = db.jobs.update_report(job_id, payload)
        if not saved:
            logger.error("Failed to save report for job %s", job_id)

        return {
            "success": saved,
            "message": "Report generated and stored" if saved else "Report generated but failed to save",
            "final_output": result.final_output,
        }


def resolve_user(db: Database, event: dict[str, Any], job_id: str, observability: Any = None) -> UserProfile:
    """``user_data`` from the event, else the job owner's profile, else defaults."""
    if event.get("user_data"):
        return UserProfile.from_row(event["user_data"])
    try:
        job = db.jobs.find_by_id(job_id)
        if job and job.get("clerk_user_id"):
            if observability:
                observability.create_event(
                    name="Reporter about to run",
                    status_message=f"Job ID: {job_id} Clerk User ID: {job['clerk_user_id']}",
                )
            return UserProfile.from_row(db.users.find_by_clerk_id(job["clerk_user_id"]))
    except Exception as exc:  # noqa: BLE001 - defaults are an intentional fallback
        logger.warning("Could not load user data: %s. Using defaults.", exc)
    return UserProfile()


def lambda_handler(event: Any, context: Any = None) -> dict[str, Any]:
    """Expects ``{"job_id": "...", "portfolio_data": {...}?, "user_data": {...}?}``."""
    with observe() as observability:
        try:
            logger.info("Reporter Lambda invoked with event: %s", json.dumps(event, default=str)[:500])
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
                observability.create_event(name="Reporter Started!", status_message="OK")

            user = resolve_user(db, event, job_id, observability)
            result = asyncio.run(run_reporter_agent(job_id, portfolio, user, db, observability))
            logger.info("Reporter completed for job %s", job_id)
            return response(200, result)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in reporter: %s", exc, exc_info=True)
            return response(500, {"success": False, "error": str(exc)})
