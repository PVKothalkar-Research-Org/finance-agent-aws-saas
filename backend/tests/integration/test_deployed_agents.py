"""Smoke tests against DEPLOYED agents. Run with: RUN_INTEGRATION=1 uv run pytest -m integration

Replaces the per-agent ``test_full.py`` scripts with assertions. Requires AWS credentials,
deployed Lambdas (terraform/6_agents) and a seeded database.
"""

import json
import os

import pytest

pytestmark = pytest.mark.integration

PREFIX = os.environ.get("RESOURCE_PREFIX", "finance-agent-aws-saas")
AGENTS = ["tagger", "reporter", "charter", "retirement"]


@pytest.fixture(scope="module")
def lambda_client():
    boto3 = pytest.importorskip("boto3")
    return boto3.client("lambda", region_name=os.environ.get("DEFAULT_AWS_REGION", "us-east-1"))


def invoke(client, agent: str, payload: dict) -> tuple[int, dict]:
    response = client.invoke(FunctionName=f"{PREFIX}-{agent}", Payload=json.dumps(payload))
    result = json.loads(response["Payload"].read())
    body = result["body"]
    return result["statusCode"], json.loads(body) if isinstance(body, str) else body


@pytest.mark.parametrize("agent", ["reporter", "charter", "retirement"])
def test_agent_rejects_missing_job_id(lambda_client, agent):
    status, body = invoke(lambda_client, agent, {})
    assert status == 400 and "job_id" in body["error"]


def test_tagger_rejects_empty_instrument_list(lambda_client):
    status, body = invoke(lambda_client, "tagger", {"instruments": []})
    assert status == 400


@pytest.mark.parametrize("agent", ["reporter", "charter", "retirement"])
def test_agent_returns_404_for_unknown_job(lambda_client, agent):
    status, _ = invoke(lambda_client, agent, {"job_id": "00000000-0000-0000-0000-000000000000"})
    assert status == 404


def test_database_data_api_roundtrip():
    from src import Database

    db = Database()
    assert db.query_raw("SELECT 1 AS ok") == [{"ok": 1}]
    assert db.instruments.find_by_symbol("SPY") is not None
