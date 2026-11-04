"""
Financial Planner Orchestrator Lambda Handler
"""

import asyncio
import json
import logging
from typing import Any

from agent_common import RetryPolicy, build_invoker, load_settings, response, with_retry
from agents import Agent, Runner, trace
from litellm.exceptions import RateLimitError

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from agent import PlannerContext, create_agent
from market import update_instrument_prices
from observability import observe
from orchestration import extract_job_id, load_portfolio_summary, tag_missing_instruments
from src import Database
from templates import ORCHESTRATOR_INSTRUCTIONS

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Composition root: the only place settings, DB and invoker are constructed.
settings = load_settings()
db = Database()
invoker = build_invoker(settings)

RETRY_POLICY = RetryPolicy(retryable=(RateLimitError,))


@with_retry(RETRY_POLICY, "Planner", logger)
async def run_orchestrator(job_id: str) -> None:
    """Run the orchestrator agent to coordinate portfolio analysis."""
    try:
        db.jobs.update_status(job_id, "running")

        await tag_missing_instruments(db, job_id, invoker, settings)

        logger.info("Planner: Updating instrument prices from market data")
        await asyncio.to_thread(update_instrument_prices, job_id, db)

        summary = await asyncio.to_thread(load_portfolio_summary, db, job_id, settings)
        model, tools, task, context = create_agent(job_id, summary, invoker, settings)

        with trace("Planner Orchestrator"):
            agent = Agent[PlannerContext](
                name="Financial Planner",
                instructions=ORCHESTRATOR_INSTRUCTIONS,
                model=model,
                tools=tools,
            )
            await Runner.run(agent, input=task, context=context, max_turns=20)
            db.jobs.update_status(job_id, "completed")
            logger.info("Planner: Job %s completed successfully", job_id)

    except Exception as exc:
        logger.error("Planner: Error in orchestration: %s", exc, exc_info=True)
        db.jobs.update_status(job_id, "failed", error_message=str(exc))
        raise


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """SQS-triggered (``{"Records": [{"body": "<job_id>"}]}``) or direct (``{"job_id": ...}``)."""
    with observe():
        try:
            logger.info("Planner Lambda invoked with event: %s", json.dumps(event, default=str)[:500])
            job_id = extract_job_id(event)
            if not job_id:
                logger.error("No job_id found in event")
                return response(400, {"error": "No job_id provided"})

            logger.info("Planner: Starting orchestration for job %s", job_id)
            asyncio.run(run_orchestrator(job_id))
            return response(200, {"success": True, "message": f"Analysis completed for job {job_id}"})
        except Exception as exc:  # noqa: BLE001
            logger.error("Planner: Error in lambda handler: %s", exc, exc_info=True)
            return response(500, {"success": False, "error": str(exc)})


# For local testing
if __name__ == "__main__":
    # Define a test user
    test_user_id = "test_user_planner_local"

    # Ensure the test user exists before creating a job
    from src.schemas import JobCreate, UserCreate
    
    user = db.users.find_by_clerk_id(test_user_id)
    if not user:
        print(f"Creating test user: {test_user_id}")
        user_create = UserCreate(clerk_user_id=test_user_id, display_name="Test Planner User")
        db.users.create(user_create.model_dump(), returning='clerk_user_id')

    # Create a test job
    print("Creating test job...")
    job_create = JobCreate(
        clerk_user_id=test_user_id,
        job_type='portfolio_analysis',
        request_payload={
            'analysis_type': 'comprehensive',
            'test': True
        }
    )
    
    job = db.jobs.create(job_create.model_dump())
    job_id = job
    
    print(f"Created test job: {job_id}")
    
    # Test the handler
    test_event = {
        'job_id': job_id
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))