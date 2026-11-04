# Executed by tests/unit/test_handler_smoke.py in a subprocess (agent modules share names, so each runs in its own interpreter).
"""Run an agent's real lambda_handler end to end with fakes for the LLM runner and database."""
import json
import os
import sys
import types

sys.path.insert(0, os.getcwd())
os.environ.update(AURORA_CLUSTER_ARN="x", AURORA_SECRET_ARN="y", AWS_DEFAULT_REGION="us-east-1", BEDROCK_REGION="us-west-2")
import lambda_handler as h

saved = {}
class FakeJobs:
    def find_by_id(self, i): return {"clerk_user_id": "u1"} if i != "missing" else None
    def update_retirement(self, i, p): saved["retirement"] = p; return 1
    def update_report(self, i, p): saved["report"] = p; return 1
    def update_charts(self, i, p): saved["charts"] = p; return 1
class FakeUsers:
    def find_by_clerk_id(self, i): return {"years_until_retirement": 12, "target_retirement_income": "65000"}
class FakeDb:
    jobs, users = FakeJobs(), FakeUsers()
    accounts = types.SimpleNamespace(find_by_user=lambda u: [{"id": "a", "account_name": "IRA", "cash_balance": "100"}])
    positions = types.SimpleNamespace(find_by_account=lambda a: [{"symbol": "VTI", "quantity": "3"}])
    instruments = types.SimpleNamespace(find_by_symbol=lambda s: {"symbol": s, "current_price": "50", "allocation_asset_class": {"equity": 100}})
h.Database = FakeDb

agent = sys.argv[1]
calls = {"n": 0}
async def fake_run(agent_obj, input, **kw):
    calls["n"] += 1
    assert "Portfolio" in input or "portfolio" in input
    out = '{"charts": [{"key": "a", "title": "T"}]}' if agent == "charter" else "# Analysis"
    return types.SimpleNamespace(final_output=out)
h.Runner.run = fake_run
if agent == "reporter":
    async def fake_eval(*a, **k): raise AssertionError("judge only runs with observability")
    h.evaluate = fake_eval

def call(event): return h.lambda_handler(event, None)
r = call({}); assert r["statusCode"] == 400, r
r = call({"job_id": "missing"}); assert r["statusCode"] == 404, r
r = call({"job_id": "j1"}); body = json.loads(r["body"]); assert r["statusCode"] == 200 and body["success"], r
r = call(json.dumps({"job_id": "j1", "portfolio_data": {"accounts": [{"name": "X", "cash_balance": 1, "positions": []}]}}))
assert r["statusCode"] == 200, r
print(agent, "OK ->", {k: (list(v) if isinstance(v, dict) else v) for k, v in saved.items()}, "runner calls:", calls["n"])
