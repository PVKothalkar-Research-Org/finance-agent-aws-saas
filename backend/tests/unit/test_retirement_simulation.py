import random

import pytest
from agent_common import Portfolio
from simulation import (
    AllocationWeights,
    calculate_asset_allocation,
    calculate_portfolio_value,
    generate_projections,
    run_monte_carlo_simulation,
)

DATA = {
    "accounts": [
        {"name": "401k", "cash_balance": 10000, "positions": [
            {"symbol": "SPY", "quantity": 100, "instrument": {"current_price": 450, "allocation_asset_class": {"equity": 100}}},
            {"symbol": "BND", "quantity": 100, "instrument": {"current_price": 75, "allocation_asset_class": {"fixed_income": 100}}},
        ]},
        {"name": "IRA", "cash_balance": 500.5, "positions": []},
    ]
}
MIXED = AllocationWeights(equity=0.6, bonds=0.3, real_estate=0.05, cash=0.05)


def test_portfolio_value_sums_cash_and_positions():
    assert calculate_portfolio_value(Portfolio.from_event(DATA)) == pytest.approx(10000 + 45000 + 7500 + 500.5)


def test_unpriced_position_uses_legacy_default_of_100():
    pf = Portfolio.from_event({"accounts": [{"cash_balance": 0, "positions": [{"symbol": "X", "quantity": 3, "instrument": {}}]}]})
    assert calculate_portfolio_value(pf) == pytest.approx(300)


def test_allocation_weights_sum_to_one_and_split_correctly():
    w = calculate_asset_allocation(Portfolio.from_event(DATA))
    total = 10000 + 45000 + 7500 + 500.5
    assert w.equity == pytest.approx(45000 / total)
    assert w.bonds == pytest.approx(7500 / total)
    assert w.cash == pytest.approx(10500.5 / total)
    assert w.equity + w.bonds + w.real_estate + w.commodities + w.cash == pytest.approx(1.0)


def test_empty_portfolio_has_zero_allocation():
    assert calculate_asset_allocation(Portfolio()) == AllocationWeights()


def test_monte_carlo_matches_golden_values_for_fixed_seed():
    """Values captured from the original implementation with random.seed(42)."""
    r = run_monte_carlo_simulation(200_000, 25, 60_000, MIXED, 300, rng=random.Random(42))
    assert (r.success_rate, r.median_final_value, r.percentile_10) == (45.0, 0, 0)
    assert r.percentile_90 == 5182729.56
    assert r.average_years_lasted == 23.3
    assert r.expected_value_at_retirement == 1352226.7


def test_monte_carlo_is_reproducible_and_seed_sensitive():
    a = run_monte_carlo_simulation(1e5, 20, 50_000, MIXED, 100, rng=random.Random(1))
    b = run_monte_carlo_simulation(1e5, 20, 50_000, MIXED, 100, rng=random.Random(1))
    c = run_monte_carlo_simulation(1e5, 20, 50_000, MIXED, 100, rng=random.Random(2))
    assert a == b and a != c


def test_higher_income_target_never_improves_success():
    low = run_monte_carlo_simulation(5e5, 20, 30_000, MIXED, 400, rng=random.Random(5))
    high = run_monte_carlo_simulation(5e5, 20, 150_000, MIXED, 400, rng=random.Random(5))
    assert low.success_rate >= high.success_rate


def test_projections_milestones_and_phases():
    p = generate_projections(200_000, 25, MIXED, 40)
    assert [x.year for x in p][:3] == [0, 5, 10]
    assert p[0].portfolio_value == 200_000 and p[0].phase == "accumulation"
    assert p[1].portfolio_value == 321275.94
    assert {x.phase for x in p} == {"accumulation", "retirement"}
    assert all(x.annual_income > 0 for x in p if x.phase == "retirement")
    assert all(x.age == 40 + x.year for x in p)
