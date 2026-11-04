"""Retirement Specialist Agent - builds the analysis prompt and model for the retirement agent."""

from __future__ import annotations

import logging
import random
from typing import Any

from agent_common import Portfolio, Settings, UserProfile, configure_bedrock_region, litellm_model_name
from agents.extensions.models.litellm_model import LitellmModel
from simulation import (
    WITHDRAWAL_RATE,
    calculate_asset_allocation,
    calculate_portfolio_value,
    generate_projections,
    run_monte_carlo_simulation,
)

logger = logging.getLogger()

NUM_SIMULATIONS = 500


def build_task(portfolio: Portfolio, user: UserProfile, rng: random.Random | None = None) -> str:
    """Run the simulations and format the analysis prompt (pure apart from ``rng``)."""
    portfolio_value = calculate_portfolio_value(portfolio)
    allocation = calculate_asset_allocation(portfolio)
    monte_carlo = run_monte_carlo_simulation(
        portfolio_value,
        user.years_until_retirement,
        user.target_retirement_income,
        allocation,
        num_simulations=NUM_SIMULATIONS,
        rng=rng,
    )
    projections = generate_projections(
        portfolio_value, user.years_until_retirement, allocation, user.current_age
    )

    allocation_text = ", ".join(f"{k.title()}: {v:.0%}" for k, v in allocation.as_dict().items() if v > 0)
    safe_income = portfolio_value * WITHDRAWAL_RATE

    task = f"""
# Portfolio Analysis Context

## Current Situation
- Portfolio Value: ${portfolio_value:,.0f}
- Asset Allocation: {allocation_text}
- Years to Retirement: {user.years_until_retirement}
- Target Annual Income: ${user.target_retirement_income:,.0f}
- Current Age: {user.current_age}

## Monte Carlo Simulation Results ({NUM_SIMULATIONS} scenarios)
- Success Rate: {monte_carlo.success_rate}% (probability of sustaining retirement income for 30 years)
- Expected Portfolio Value at Retirement: ${monte_carlo.expected_value_at_retirement:,.0f}
- 10th Percentile Outcome: ${monte_carlo.percentile_10:,.0f} (worst case)
- Median Final Value: ${monte_carlo.median_final_value:,.0f}
- 90th Percentile Outcome: ${monte_carlo.percentile_90:,.0f} (best case)
- Average Years Portfolio Lasts: {monte_carlo.average_years_lasted} years

## Key Projections (Milestones)
"""
    for proj in projections[:6]:
        if proj.phase == "accumulation":
            task += f"- Age {proj.age}: ${proj.portfolio_value:,.0f} (building wealth)\n"
        else:
            task += (
                f"- Age {proj.age}: ${proj.portfolio_value:,.0f} "
                f"(annual income: ${proj.annual_income:,.0f})\n"
            )

    task += f"""

## Risk Factors to Consider
- Sequence of returns risk (poor returns early in retirement)
- Inflation impact (3% assumed)
- Healthcare costs in retirement
- Longevity risk (living beyond 30 years)
- Market volatility (equity standard deviation: 18%)

## Safe Withdrawal Rate Analysis
- 4% Rule: ${safe_income:,.0f} initial annual income
- Target Income: ${user.target_retirement_income:,.0f}
- Gap: ${user.target_retirement_income - safe_income:,.0f}

Your task: Analyze this retirement readiness data and provide a comprehensive retirement analysis including:
1. Clear assessment of retirement readiness
2. Specific recommendations to improve success rate
3. Risk mitigation strategies
4. Action items with timeline

Provide your analysis in clear markdown format with specific numbers and actionable recommendations.
"""
    return task


def create_agent(
    job_id: str, portfolio: Portfolio, user: UserProfile, settings: Settings
) -> tuple[LitellmModel, list[Any], str]:
    """Create the model, (empty) tool list and task prompt for the retirement agent."""
    configure_bedrock_region(settings)
    model = LitellmModel(model=litellm_model_name(settings))
    logger.info("Retirement: building task for job %s", job_id)
    return model, [], build_task(portfolio, user)
