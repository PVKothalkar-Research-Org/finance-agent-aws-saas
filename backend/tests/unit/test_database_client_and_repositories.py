import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from src.client import DataAPIClient
from src.models import Database, JobRepository, PositionRepository, Repository, UserRepository


@pytest.fixture
def client(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr("src.client.boto3.client", lambda *a, **k: fake)
    c = DataAPIClient(cluster_arn="arn:cluster", secret_arn="arn:secret", database="finance_agent_aws_saas")
    c._fake = fake  # type: ignore[attr-defined]
    return c


def test_missing_configuration_raises(monkeypatch):
    monkeypatch.delenv("AURORA_CLUSTER_ARN", raising=False)
    monkeypatch.delenv("AURORA_SECRET_ARN", raising=False)
    with pytest.raises(ValueError, match="Missing required Aurora configuration"):
        DataAPIClient()


def test_default_database_name_has_no_hyphens(monkeypatch):
    monkeypatch.delenv("AURORA_DATABASE", raising=False)
    monkeypatch.setattr("src.client.boto3.client", lambda *a, **k: MagicMock())
    assert DataAPIClient("a", "b").database == "finance_agent_aws_saas"


@pytest.mark.parametrize("value,expected", [
    (None, {"isNull": True}), (True, {"booleanValue": True}), (3, {"longValue": 3}), (1.5, {"doubleValue": 1.5}),
    (Decimal("2.50"), {"stringValue": "2.50"}), (date(2026, 1, 2), {"stringValue": "2026-01-02"}),
    ({"a": 1}, {"stringValue": '{"a": 1}'}), ("x", {"stringValue": "x"}),
])
def test_build_parameters(client, value, expected):
    assert client._build_parameters({"k": value}) == [{"name": "k", "value": expected}]


@pytest.mark.parametrize("field,expected", [
    ({"isNull": True}, None), ({"longValue": 7}, 7), ({"stringValue": "plain"}, "plain"),
    ({"stringValue": '{"equity": 100}'}, {"equity": 100}), ({"stringValue": "[1, 2]"}, [1, 2]),
    ({"stringValue": "{broken"}, "{broken"),
])
def test_extract_value(client, field, expected):
    assert client._extract_value(field) == expected


def test_query_maps_columns_to_values(client):
    client._fake.execute_statement.return_value = {
        "columnMetadata": [{"name": "symbol"}, {"name": "qty"}],
        "records": [[{"stringValue": "VTI"}, {"longValue": 2}], [{"stringValue": "BND"}, {"isNull": True}]],
    }
    assert client.query("SELECT 1") == [{"symbol": "VTI", "qty": 2}, {"symbol": "BND", "qty": None}]
    assert client.query_one("SELECT 1") == {"symbol": "VTI", "qty": 2}


def test_insert_casts_complex_types(client):
    client._fake.execute_statement.return_value = {"records": [[{"stringValue": "abc"}]]}
    returned = client.insert("jobs", {"payload": {"a": 1}, "price": Decimal("1.5"), "d": date(2026, 1, 1),
                                      "ts": datetime(2026, 1, 1, 1, 1), "plain": "x"}, returning="id")
    sql = client._fake.execute_statement.call_args.kwargs["sql"]
    assert ":payload::jsonb" in sql and ":price::numeric" in sql and ":d::date" in sql and ":ts::timestamp" in sql
    assert "RETURNING id" in sql and returned == "abc"


def test_update_returns_row_count_and_merges_params(client):
    client._fake.execute_statement.return_value = {"numberOfRecordsUpdated": 1}
    assert client.update("users", {"display_name": "A"}, "clerk_user_id = :cid", {"cid": "u1"}) == 1
    params = {p["name"] for p in client._fake.execute_statement.call_args.kwargs["parameters"]}
    assert params == {"display_name", "cid"}


class StubClient:
    def __init__(self):
        self.calls = []

    def query(self, sql, params=None):
        self.calls.append(("query", sql, params)); return [{"id": 1}]

    def query_one(self, sql, params=None):
        self.calls.append(("query_one", sql, params)); return {"id": 1}

    def update(self, table, data, where, params):
        self.calls.append(("update", table, data, where, params)); return 1

    def insert(self, table, data, returning=None):
        self.calls.append(("insert", table, data, returning)); return "new-id"


def test_repository_requires_table_name():
    class Bad(Repository[dict]):
        pass

    with pytest.raises(ValueError):
        Bad(StubClient())  # type: ignore[arg-type]


def test_job_status_timestamps():
    stub = StubClient(); jobs = JobRepository(stub)  # type: ignore[arg-type]
    jobs.update_status("j", "running")
    jobs.update_status("j", "failed", error_message="boom")
    running, failed = stub.calls[0][2], stub.calls[1][2]
    assert "started_at" in running and "completed_at" not in running
    assert "completed_at" in failed and failed["error_message"] == "boom"


def test_create_user_drops_none_values_and_find_uses_parameters():
    stub = StubClient(); users = UserRepository(stub)  # type: ignore[arg-type]
    assert users.create_user("u1", display_name="Ann") == "new-id"
    assert stub.calls[0][2] == {"clerk_user_id": "u1", "display_name": "Ann"}
    users.find_by_clerk_id("u1'; DROP TABLE users;--")
    sql, params = stub.calls[1][1], stub.calls[1][2]
    assert "DROP" not in sql and params[0]["value"]["stringValue"].startswith("u1'")


def test_position_value_handles_empty_result():
    stub = StubClient(); stub.query_one = lambda sql, params=None: None  # type: ignore[method-assign]
    assert PositionRepository(stub).get_portfolio_value("a") == {"num_positions": 0, "total_value": 0, "total_shares": 0}  # type: ignore[arg-type]


def test_database_facade_wires_repositories(monkeypatch):
    monkeypatch.setattr("src.client.boto3.client", lambda *a, **k: MagicMock())
    db = Database("a", "b", "finance_agent_aws_saas")
    assert {db.users.table_name, db.instruments.table_name, db.accounts.table_name, db.positions.table_name, db.jobs.table_name} == {
        "users", "instruments", "accounts", "positions", "jobs"}
    json.dumps(db.jobs.table_name)
