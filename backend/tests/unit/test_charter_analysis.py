import json

import pytest
from agent_common import Portfolio
from analysis import analyze_portfolio, extract_charts

PF = Portfolio.from_event({"accounts": [
    {"name": "401k", "type": "retirement", "cash_balance": 100, "positions": [
        {"symbol": "VTI", "quantity": 10, "instrument": {"current_price": 20, "allocation_asset_class": {"equity": 100},
                                                           "allocation_regions": {"north_america": 100}, "allocation_sectors": {"technology": 50, "other": 50}}},
        {"symbol": "NOPRICE", "quantity": 4, "instrument": {"allocation_asset_class": {"fixed_income": 100}}}]},
    {"name": "401k", "type": "retirement", "cash_balance": 50, "positions": []},
]})


def test_analysis_merges_same_name_accounts_and_defaults_price_to_one():
    text = analyze_portfolio(PF)
    assert "Total Value: $354.00" in text  # 150 cash + 200 + 4*1.0
    assert "Number of Accounts: 1" in text and "Number of Positions: 2" in text
    assert "  401k (retirement): $354.00 (100.0%)" in text
    assert "  VTI: $200.00 (56.5%)" in text


def test_analysis_aggregates_allocations_with_cash():
    text = analyze_portfolio(PF)
    assert "  equity: $200.00" in text and "  fixed_income: $4.00" in text and "  cash: $150.00" in text
    assert "  north_america: $200.00" in text and "  technology: $100.00" in text


def test_extract_charts_from_wrapped_json():
    payload = {"charts": [{"key": "pie", "title": "A"}, {"title": "no key"}]}
    out = extract_charts("Here you go:\n" + json.dumps(payload) + "\nThanks")
    assert out == {"pie": {"title": "A"}, "chart_2": {"title": "no key"}}


@pytest.mark.parametrize("bad", [None, "", "no json here", "{broken json}", '{"charts": []}'])
def test_extract_charts_returns_empty_for_unusable_output(bad):
    assert extract_charts(bad) == {}
