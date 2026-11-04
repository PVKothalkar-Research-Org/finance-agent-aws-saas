import pytest
from agent_common import BadRequestError, JobNotFoundError, resolve_portfolio


def test_event_portfolio_takes_precedence(fake_db):
    event = {"portfolio_data": {"accounts": [{"name": "X", "cash_balance": 5, "positions": []}]}}
    pf = resolve_portfolio(fake_db(job=False), event, "j1")  # DB would 404 - proves it is not consulted
    assert pf.accounts[0].name == "X" and pf.cash_balance == 5


def test_loads_from_database_when_event_has_none(fake_db):
    pf = resolve_portfolio(fake_db(), {}, "job-1")
    assert pf.user_id == "user-1" and pf.job_id == "job-1" and pf.total_value() == pytest.approx(70.0)
    assert pf.user.years_until_retirement == 20


def test_unknown_job_maps_to_not_found(fake_db):
    with pytest.raises(JobNotFoundError):
        resolve_portfolio(fake_db(job=False), {}, "nope")


def test_other_database_failures_map_to_bad_request(fake_db):
    db = fake_db()

    def boom(_id):
        raise RuntimeError("data api down")

    db.accounts.find_by_user = boom
    with pytest.raises(BadRequestError, match="No portfolio data provided"):
        resolve_portfolio(db, {}, "job-1")


def test_positions_without_instrument_row_are_skipped(fake_db):
    db = fake_db(positions=[{"symbol": "GHOST", "quantity": "9"}, {"symbol": "VTI", "quantity": "1"}])
    assert [p.symbol for p in resolve_portfolio(db, {}, "job-1").accounts[0].positions] == ["VTI"]
