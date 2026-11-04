import pytest
from agent_common import MockInvoker, load_settings
from orchestration import (
    InstrumentToTag,
    agent_specs,
    build_task,
    extract_job_id,
    find_instruments_needing_tags,
    load_portfolio_summary,
    run_specialist,
    tag_missing_instruments,
)

SETTINGS = load_settings({})


def test_finds_unknown_and_untagged_instruments(fake_db):
    db = fake_db(
        positions=[{"symbol": "VTI", "quantity": "1"}, {"symbol": "NEW", "quantity": "1"}, {"symbol": "BARE", "quantity": "1"}],
        instruments={"VTI": {"symbol": "VTI", "allocation_asset_class": {"equity": 100}, "allocation_regions": {"na": 100}, "allocation_sectors": {"tech": 100}},
                     "BARE": {"symbol": "BARE", "name": "Bare ETF"}},
    )
    assert find_instruments_needing_tags(db, "job-1") == [InstrumentToTag("NEW"), InstrumentToTag("BARE", "Bare ETF")]


async def test_tagger_called_only_when_needed(fake_db):
    inv = MockInvoker()
    assert await tag_missing_instruments(fake_db(), "job-1", inv, SETTINGS) == 0 and inv.calls == []
    db = fake_db(positions=[{"symbol": "NEW", "quantity": "1"}])
    assert await tag_missing_instruments(db, "job-1", inv, SETTINGS) == 1
    name, fn, payload = inv.calls[0]
    assert (name, fn) == ("Tagger", "finance-agent-aws-saas-tagger")
    assert payload == {"instruments": [{"symbol": "NEW", "name": ""}]}


async def test_missing_job_is_logged_not_raised(fake_db):
    assert await tag_missing_instruments(fake_db(job=False), "x", MockInvoker(), SETTINGS) == 0


async def test_run_specialist_success_and_error_messages():
    spec = agent_specs(SETTINGS)["reporter"]
    inv = MockInvoker()
    assert "completed successfully" in await run_specialist(inv, spec, "j1")
    assert inv.calls[0][2] == {"job_id": "j1"}

    class Failing:
        async def invoke(self, *a):
            return {"error": "throttled"}

    assert await run_specialist(Failing(), spec, "j1") == "Reporter agent failed: throttled"


def test_function_names_follow_settings():
    s = load_settings({"CHARTER_FUNCTION": "custom-charter"})
    assert agent_specs(s)["charter"].function_name == "custom-charter"


def test_portfolio_summary_totals(fake_db):
    s = load_portfolio_summary(fake_db(), "job-1", SETTINGS)
    assert (s.num_accounts, s.num_positions, s.years_until_retirement) == (1, 1, 20)
    assert s.total_value == pytest.approx(70.0) and s.target_retirement_income == 70000.0
    assert "1 positions" in build_task("job-1", s) and "20 years" in build_task("job-1", s)


def test_portfolio_summary_errors(fake_db):
    with pytest.raises(LookupError):
        load_portfolio_summary(fake_db(job=False), "x", SETTINGS)
    with pytest.raises(LookupError):
        db = fake_db()
        db.users.find_by_clerk_id = lambda _id: None
        load_portfolio_summary(db, "job-1", SETTINGS)


@pytest.mark.parametrize("event,expected", [
    ({"job_id": "j1"}, "j1"),
    ({"Records": [{"body": "j2"}]}, "j2"),
    ({"Records": [{"body": '{"job_id": "j3"}'}]}, "j3"),
    ({"Records": [{"body": "{not json"}]}, "{not json"),
    ({}, None),
])
def test_extract_job_id(event, expected):
    assert extract_job_id(event) == expected
