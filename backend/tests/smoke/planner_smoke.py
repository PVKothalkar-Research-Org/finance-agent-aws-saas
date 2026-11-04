# Executed by tests/unit/test_handler_smoke.py in a subprocess (agent modules share names, so each runs in its own interpreter).
import json
import os
import sys
import types

sys.path.insert(0, os.getcwd())
os.environ.update(AURORA_CLUSTER_ARN="x", AURORA_SECRET_ARN="y", AWS_DEFAULT_REGION="us-east-1", MOCK_LAMBDAS="true", POLYGON_API_KEY="k")
import lambda_handler as h
from agent_common import MockInvoker

assert isinstance(h.invoker, MockInvoker), "MOCK_LAMBDAS should select the mock at the composition root"
status = []
class Jobs:
    def find_by_id(self, i): return {"clerk_user_id": "u1"}
    def update_status(self, i, s, error_message=None): status.append((s, error_message))
class Db:
    jobs = Jobs()
    users = types.SimpleNamespace(find_by_clerk_id=lambda u: {"years_until_retirement": 20, "target_retirement_income": "70000"})
    accounts = types.SimpleNamespace(find_by_user=lambda u: [{"id": "a", "cash_balance": "10"}])
    positions = types.SimpleNamespace(find_by_account=lambda a: [{"symbol": "NEW", "quantity": "2"}])
    instruments = types.SimpleNamespace(find_by_symbol=lambda s: {"symbol": s, "current_price": "5"})
h.db = Db()
h.update_instrument_prices = lambda job_id, db: None
async def fake_run(agent, input, context=None, **kw):
    # emulate the LLM calling the three tools through the injected invoker
    from orchestration import agent_specs, run_specialist
    msgs = [await run_specialist(context.invoker, s, context.job_id) for s in agent_specs(context.settings).values()]
    assert all("completed successfully" in m for m in msgs), msgs
    return types.SimpleNamespace(final_output="Done")
h.Runner.run = fake_run
r = h.lambda_handler({"Records": [{"body": json.dumps({"job_id": "j9"})}]}, None)
assert r["statusCode"] == 200, r
assert status == [("running", None), ("completed", None)], status
names = [c[0] for c in h.invoker.calls]
assert names == ["Tagger", "Reporter", "Charter", "Retirement"], names
r = h.lambda_handler({}, None); assert r["statusCode"] == 400
print("planner OK", status, names)
