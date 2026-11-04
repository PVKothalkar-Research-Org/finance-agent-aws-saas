"""Pure retirement maths: portfolio value, allocation, Monte Carlo and projections.

No SDK or AWS imports so it can be unit-tested offline and reused by any entrypoint.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from agent_common import Portfolio

DEFAULT_PRICE = 100.0  # legacy behaviour: unpriced instruments are valued at $100
ANNUAL_CONTRIBUTION = 10_000.0
INFLATION_RATE = 0.03
RETIREMENT_YEARS = 30
CASH_RETURN = 0.02
WITHDRAWAL_RATE = 0.04
MILESTONE_STEP_YEARS = 5


@dataclass(frozen=True, slots=True)
class AssetReturn:
    mean: float
    std: float


@dataclass(frozen=True, slots=True)
class ReturnAssumptions:
    equity: AssetReturn = AssetReturn(0.07, 0.18)
    bonds: AssetReturn = AssetReturn(0.04, 0.05)
    real_estate: AssetReturn = AssetReturn(0.06, 0.12)
    cash: float = CASH_RETURN


DEFAULT_ASSUMPTIONS = ReturnAssumptions()


@dataclass(frozen=True, slots=True)
class AllocationWeights:
    """Fractions (0-1) of total portfolio value by asset class."""

    equity: float = 0.0
    bonds: float = 0.0
    real_estate: float = 0.0
    commodities: float = 0.0
    cash: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "equity": self.equity,
            "bonds": self.bonds,
            "real_estate": self.real_estate,
            "commodities": self.commodities,
            "cash": self.cash,
        }

    def expected_return(self, a: ReturnAssumptions = DEFAULT_ASSUMPTIONS) -> float:
        return (
            self.equity * a.equity.mean
            + self.bonds * a.bonds.mean
            + self.real_estate * a.real_estate.mean
            + self.cash * a.cash
        )


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    success_rate: float
    median_final_value: float
    percentile_10: float
    percentile_90: float
    average_years_lasted: float
    expected_value_at_retirement: float


@dataclass(frozen=True, slots=True)
class Projection:
    year: int
    age: int
    portfolio_value: float
    annual_income: float
    phase: str


def calculate_portfolio_value(portfolio: Portfolio) -> float:
    return portfolio.total_value(default_price=DEFAULT_PRICE)


def calculate_asset_allocation(portfolio: Portfolio) -> AllocationWeights:
    total_value = portfolio.total_value(default_price=DEFAULT_PRICE)
    if total_value == 0:
        return AllocationWeights()

    equity = bonds = real_estate = commodities = 0.0
    for account in portfolio.accounts:
        for position in account.positions:
            value = position.value(default_price=DEFAULT_PRICE)
            if position.instrument is None:
                continue
            ac = position.instrument.asset_class
            equity += value * ac.pct("equity") / 100
            bonds += value * ac.pct("fixed_income") / 100
            real_estate += value * ac.pct("real_estate") / 100
            commodities += value * ac.pct("commodities") / 100

    return AllocationWeights(
        equity=equity / total_value,
        bonds=bonds / total_value,
        real_estate=real_estate / total_value,
        commodities=commodities / total_value,
        cash=portfolio.cash_balance / total_value,
    )


def _sample_portfolio_return(
    weights: AllocationWeights, assumptions: ReturnAssumptions, rng: random.Random
) -> float:
    equity = rng.gauss(assumptions.equity.mean, assumptions.equity.std)
    bond = rng.gauss(assumptions.bonds.mean, assumptions.bonds.std)
    real_estate = rng.gauss(assumptions.real_estate.mean, assumptions.real_estate.std)
    return (
        weights.equity * equity
        + weights.bonds * bond
        + weights.real_estate * real_estate
        + weights.cash * assumptions.cash
    )


def run_monte_carlo_simulation(
    current_value: float,
    years_until_retirement: int,
    target_annual_income: float,
    weights: AllocationWeights,
    num_simulations: int = 500,
    assumptions: ReturnAssumptions = DEFAULT_ASSUMPTIONS,
    rng: random.Random | None = None,
) -> MonteCarloResult:
    """Simulate accumulation then 30 years of inflation-adjusted withdrawals."""
    rng = rng or random.Random()
    successful = 0
    final_values: list[float] = []
    years_lasted: list[int] = []

    for _ in range(num_simulations):
        value = current_value
        for _ in range(years_until_retirement):
            value = value * (1 + _sample_portfolio_return(weights, assumptions, rng))
            value += ANNUAL_CONTRIBUTION

        withdrawal = target_annual_income
        lasted = 0
        for _ in range(RETIREMENT_YEARS):
            if value <= 0:
                break
            withdrawal *= 1 + INFLATION_RATE
            value = value * (1 + _sample_portfolio_return(weights, assumptions, rng)) - withdrawal
            if value > 0:
                lasted += 1

        final_values.append(max(0.0, value))
        years_lasted.append(lasted)
        if lasted >= RETIREMENT_YEARS:
            successful += 1

    final_values.sort()
    expected = weights.expected_return(assumptions)
    expected_at_retirement = current_value
    for _ in range(years_until_retirement):
        expected_at_retirement = expected_at_retirement * (1 + expected) + ANNUAL_CONTRIBUTION

    n = num_simulations
    return MonteCarloResult(
        success_rate=round(successful / n * 100, 1),
        median_final_value=round(final_values[n // 2], 2),
        percentile_10=round(final_values[n // 10], 2),
        percentile_90=round(final_values[9 * n // 10], 2),
        average_years_lasted=round(sum(years_lasted) / len(years_lasted), 1),
        expected_value_at_retirement=round(expected_at_retirement, 2),
    )


def generate_projections(
    current_value: float,
    years_until_retirement: int,
    weights: AllocationWeights,
    current_age: int,
    assumptions: ReturnAssumptions = DEFAULT_ASSUMPTIONS,
) -> list[Projection]:
    """Milestone projections every 5 years through 30 years past retirement."""
    expected = weights.expected_return(assumptions)
    value = current_value
    projections: list[Projection] = []

    for year in range(0, years_until_retirement + RETIREMENT_YEARS + 1, MILESTONE_STEP_YEARS):
        if year <= years_until_retirement:
            for _ in range(min(MILESTONE_STEP_YEARS, year)):
                value = value * (1 + expected) + ANNUAL_CONTRIBUTION
            phase, income = "accumulation", 0.0
        else:
            income = value * WITHDRAWAL_RATE
            for _ in range(min(MILESTONE_STEP_YEARS, year - years_until_retirement)):
                value = value * (1 + expected) - income
            phase = "retirement"

        if value > 0:
            projections.append(
                Projection(year, current_age + year, round(value, 2), round(income, 2), phase)
            )
    return projections
