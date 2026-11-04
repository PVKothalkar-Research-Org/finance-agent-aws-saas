import pytest
from agent_common import Instrument, Portfolio, UserProfile
from metrics import calculate_portfolio_metrics, describe_allocations, format_portfolio_for_analysis

PF = Portfolio.from_event({"accounts": [
    {"name": "401k", "cash_balance": 100, "positions": [
        {"symbol": "VTI", "quantity": 10, "instrument": {"current_price": 20, "allocation_asset_class": {"equity": 100},
                                                           "allocation_regions": {"north_america": 60, "europe": 30, "asia": 10}}},
        {"symbol": "XYZ", "quantity": 5, "instrument": {}}]},
    {"name": "Taxable", "cash_balance": 50, "positions": [{"symbol": "VTI", "quantity": 1, "instrument": {"current_price": 20}}]},
]})


def test_metrics_count_only_priced_positions():
    m = calculate_portfolio_metrics(PF)
    assert (m.num_accounts, m.num_positions, m.unique_symbols) == (2, 3, 2)
    assert m.cash_balance == 150 and m.total_value == pytest.approx(150 + 200 + 20)


def test_describe_allocations_top_two_regions():
    text = describe_allocations(PF.accounts[0].positions[0].instrument)
    assert text == " (Asset: equity, Regions: north_america 60%, europe 30%)"
    assert describe_allocations(None) == "" and describe_allocations(Instrument(symbol="Q")) == ""


def test_prompt_contains_overview_and_user_profile():
    text = format_portfolio_for_analysis(PF, UserProfile(years_until_retirement=25, target_retirement_income=75000))
    assert "- 2 accounts" in text and "- $370.00 total value" in text
    assert "401k ($100.00 cash):" in text and "  - VTI: 10.00 shares (Asset: equity" in text
    assert "Years to retirement: 25" in text and "$75,000/year" in text


def test_total_value_line_blank_for_empty_portfolio():
    assert "total value" not in format_portfolio_for_analysis(Portfolio(), UserProfile())
