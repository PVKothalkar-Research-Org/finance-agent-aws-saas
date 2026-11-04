from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from src.schemas import AccountCreate, InstrumentCreate, JobCreate, PositionCreate, UserCreate

VALID = dict(
    symbol="SPY", name="SPDR S&P 500", instrument_type="etf", current_price=Decimal("450.10"),
    allocation_regions={"north_america": 100}, allocation_sectors={"technology": 40, "healthcare": 30, "financials": 30},
    allocation_asset_class={"equity": 100},
)


def test_instrument_valid():
    assert InstrumentCreate(**VALID).symbol == "SPY"


@pytest.mark.parametrize("field,bad", [
    ("allocation_regions", {}),
    ("allocation_regions", {"europe": 40}),
    ("allocation_regions", {"mars": 100}),
    ("symbol", ""),
    ("current_price", Decimal("-1")),
    ("instrument_type", "nft"),
])
def test_instrument_rejects_invalid(field, bad):
    with pytest.raises(ValidationError):
        InstrumentCreate(**{**VALID, field: bad})


def test_user_defaults_are_independent_per_instance():
    a, b = UserCreate(clerk_user_id="a"), UserCreate(clerk_user_id="b")
    a.asset_class_targets["equity"] = 1  # type: ignore[index]
    assert b.asset_class_targets == {"equity": 70.0, "fixed_income": 30.0}


def test_user_bounds():
    with pytest.raises(ValidationError):
        UserCreate(clerk_user_id="u", years_until_retirement=101)
    with pytest.raises(ValidationError):
        UserCreate(clerk_user_id="u", target_retirement_income=Decimal("-5"))


def test_account_and_position_constraints():
    assert AccountCreate(account_name="401k").cash_balance == 0
    with pytest.raises(ValidationError):
        AccountCreate(account_name="x", cash_interest=Decimal("1.5"))
    with pytest.raises(ValidationError):
        PositionCreate(account_id="a", symbol="SPY", quantity=Decimal("0"))
    assert PositionCreate(account_id="a", symbol="SPY", quantity=Decimal("1.5")).as_of_date == date.today()


def test_job_type_validated():
    assert JobCreate(clerk_user_id="u", job_type="portfolio_analysis").request_payload is None
    with pytest.raises(ValidationError):
        JobCreate(clerk_user_id="u", job_type="bogus")
