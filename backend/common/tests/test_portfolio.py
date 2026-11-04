import pytest
from agent_common import Instrument, Portfolio, Position, UserProfile, load_portfolio
from agent_common.portfolio import JobNotFoundError


def make_portfolio(price=None):
    inst = Instrument(symbol="VTI", current_price=price)
    return Portfolio.from_event(
        {
            "accounts": [
                {
                    "name": "401k",
                    "cash_balance": "100.5",
                    "positions": [{"symbol": "VTI", "quantity": "10", "instrument": inst.model_dump() | {"current_price": price}}],
                }
            ]
        }
    )


def test_total_value_with_price() -> None:
    assert make_portfolio(price=20.0).total_value() == pytest.approx(300.5)


def test_total_value_missing_price_defaults_to_zero_or_given_default() -> None:
    p = make_portfolio(price=None)
    assert p.total_value() == pytest.approx(100.5)
    assert p.total_value(default_price=100.0) == pytest.approx(1100.5)


def test_unique_symbols_and_counts() -> None:
    p = make_portfolio(1.0)
    assert p.unique_symbols == {"VTI"} and p.num_positions == 1


def test_user_profile_defaults_and_row() -> None:
    assert UserProfile.from_row(None).years_until_retirement == 30
    u = UserProfile.from_row({"years_until_retirement": 12, "target_retirement_income": "95000.5"})
    assert (u.years_until_retirement, u.target_retirement_income) == (12, 95000.5)


def test_instrument_from_row_parses_strings_and_allocations() -> None:
    i = Instrument.from_row(
        {"symbol": "BND", "current_price": "72.1", "allocation_asset_class": {"fixed_income": 100},
         "allocation_regions": {"north_america": 100}, "allocation_sectors": {"treasury": 100}}
    )
    assert i.current_price == 72.1 and i.has_allocations and i.asset_class.pct("fixed_income") == 100


def test_position_value_without_instrument() -> None:
    assert Position(symbol="X", quantity=5).value() == 0.0


class _Repo:
    def __init__(self, **m) -> None: self.m = m
    def __getattr__(self, name):
        if name in self.m: return self.m[name]
        raise AttributeError(name)


class FakeDb:
    def __init__(self, job=True) -> None:
        self.jobs = _Repo(find_by_id=lambda j: {"clerk_user_id": "u1"} if job else None)
        self.users = _Repo(find_by_clerk_id=lambda u: {"years_until_retirement": 20})
        self.accounts = _Repo(find_by_user=lambda u: [{"id": "a1", "account_name": "IRA", "cash_balance": "50"}])
        self.positions = _Repo(find_by_account=lambda a: [{"symbol": "VTI", "quantity": "2"}, {"symbol": "ZZZ", "quantity": "1"}])
        self.instruments = _Repo(find_by_symbol=lambda s: {"symbol": s, "current_price": "10"} if s == "VTI" else None)


def test_load_portfolio_skips_unknown_instruments() -> None:
    p = load_portfolio(FakeDb(), "j1")
    assert p.user.years_until_retirement == 20
    assert [x.symbol for x in p.accounts[0].positions] == ["VTI"]
    assert p.total_value() == pytest.approx(70.0)


def test_load_portfolio_missing_job() -> None:
    with pytest.raises(JobNotFoundError):
        load_portfolio(FakeDb(job=False), "nope")
