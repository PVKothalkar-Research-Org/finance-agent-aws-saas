"""Pure planner logic: what needs tagging, portfolio summary, task prompt, agent dispatch.

No Agents-SDK imports, so everything here is unit-testable with fakes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from agent_common import AgentInvoker, JobNotFoundError, Settings

logger = logging.getLogger()


@dataclass(frozen=True, slots=True)
class PortfolioSummary:
    total_value: float
    num_accounts: int
    num_positions: int
    years_until_retirement: int
    target_retirement_income: float


@dataclass(frozen=True, slots=True)
class InstrumentToTag:
    symbol: str
    name: str = ""

    def to_payload(self) -> dict[str, str]:
        return {"symbol": self.symbol, "name": self.name}


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """How the planner calls one specialist agent."""

    display_name: str
    function_name: str
    success_message: str


def agent_specs(settings: Settings) -> dict[str, AgentSpec]:
    return {
        "reporter": AgentSpec(
            "Reporter",
            settings.reporter_function,
            "Reporter agent completed successfully. Portfolio analysis narrative has been generated and saved.",
        ),
        "charter": AgentSpec(
            "Charter",
            settings.charter_function,
            "Charter agent completed successfully. Portfolio visualizations have been created and saved.",
        ),
        "retirement": AgentSpec(
            "Retirement",
            settings.retirement_function,
            "Retirement agent completed successfully. Retirement projections have been calculated and saved.",
        ),
    }


async def run_specialist(invoker: AgentInvoker, spec: AgentSpec, job_id: str) -> str:
    """Invoke a specialist and turn the result into the message the LLM sees."""
    result = await invoker.invoke(spec.display_name, spec.function_name, {"job_id": job_id})
    if "error" in result:
        return f"{spec.display_name} agent failed: {result['error']}"
    return spec.success_message


def find_instruments_needing_tags(db: Any, job_id: str) -> list[InstrumentToTag]:
    """Instruments in the job owner's portfolio lacking region/sector/asset-class data."""
    job = db.jobs.find_by_id(job_id)
    if not job:
        raise JobNotFoundError(f"Job {job_id} not found")

    missing: list[InstrumentToTag] = []
    for account in db.accounts.find_by_user(job["clerk_user_id"]):
        for position in db.positions.find_by_account(account["id"]):
            instrument = db.instruments.find_by_symbol(position["symbol"])
            if not instrument:
                missing.append(InstrumentToTag(position["symbol"]))
            elif not (
                instrument.get("allocation_regions")
                and instrument.get("allocation_sectors")
                and instrument.get("allocation_asset_class")
            ):
                missing.append(InstrumentToTag(position["symbol"], instrument.get("name", "")))
    return missing


async def tag_missing_instruments(db: Any, job_id: str, invoker: AgentInvoker, settings: Settings) -> int:
    """Call the tagger for untagged instruments. Returns how many were sent."""
    try:
        missing = find_instruments_needing_tags(db, job_id)
    except JobNotFoundError:
        logger.error("Job %s not found", job_id)
        return 0
    if not missing:
        logger.info("Planner: All instruments have allocation data")
        return 0

    logger.info("Planner: %d instruments need classification: %s", len(missing), [m.symbol for m in missing])
    result = await invoker.invoke(
        "Tagger", settings.tagger_function, {"instruments": [m.to_payload() for m in missing]}
    )
    if "error" in result:
        logger.error("Planner: Error tagging instruments: %s", result["error"])
    else:
        logger.info("Planner: InstrumentTagger completed - Tagged %d instruments", len(missing))
    return len(missing)


def load_portfolio_summary(db: Any, job_id: str, settings: Settings) -> PortfolioSummary:
    job = db.jobs.find_by_id(job_id)
    if not job:
        raise JobNotFoundError(f"Job {job_id} not found")
    user_id = job["clerk_user_id"]
    user = db.users.find_by_clerk_id(user_id)
    if not user:
        raise LookupError(f"User {user_id} not found")

    accounts = db.accounts.find_by_user(user_id)
    total_value = 0.0
    num_positions = 0
    for account in accounts:
        total_value += float(account.get("cash_balance", 0))
        positions = db.positions.find_by_account(account["id"])
        num_positions += len(positions)
        for position in positions:
            instrument = db.instruments.find_by_symbol(position["symbol"])
            if instrument and instrument.get("current_price"):
                total_value += float(instrument["current_price"]) * float(position["quantity"])

    return PortfolioSummary(
        total_value=total_value,
        num_accounts=len(accounts),
        num_positions=num_positions,
        years_until_retirement=user.get("years_until_retirement", settings.default_years_until_retirement),
        target_retirement_income=float(
            user.get("target_retirement_income", settings.default_target_retirement_income)
        ),
    )


def build_task(job_id: str, summary: PortfolioSummary) -> str:
    return f"""Job {job_id} has {summary.num_positions} positions.
Retirement: {summary.years_until_retirement} years.

Call the appropriate agents."""


def extract_job_id(event: dict[str, Any]) -> str | None:
    """Job id from an SQS record (plain or JSON body) or a direct invocation."""
    if event.get("Records"):
        body = event["Records"][0]["body"]
        if isinstance(body, str) and body.startswith("{"):
            try:
                return json.loads(body).get("job_id", body)
            except json.JSONDecodeError:
                return body
        return body
    return event.get("job_id")
