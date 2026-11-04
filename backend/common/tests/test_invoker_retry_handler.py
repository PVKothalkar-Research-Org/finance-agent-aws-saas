import io
import json
import logging

import pytest
from agent_common import (
    AgentTemporaryError,
    BadRequestError,
    BaseLambdaHandler,
    LambdaInvoker,
    MockInvoker,
    RetryPolicy,
    build_invoker,
    load_settings,
    with_retry,
)
from tenacity import RetryError

FAST = RetryPolicy(max_attempts=3, wait_min=0, wait_max=0, wait_multiplier=0)


class FakeLambda:
    def __init__(self, payload) -> None: self.payload, self.calls = payload, []
    def invoke(self, **kw):
        self.calls.append(kw)
        return {"Payload": io.BytesIO(json.dumps(self.payload).encode())}


async def test_lambda_invoker_unwraps_envelope() -> None:
    client = FakeLambda({"statusCode": 200, "body": json.dumps({"ok": 1})})
    assert await LambdaInvoker(client).invoke("A", "fn", {"job_id": "1"}) == {"ok": 1}
    assert client.calls[0]["FunctionName"] == "fn"


async def test_lambda_invoker_returns_error_dict() -> None:
    class Boom:
        def invoke(self, **kw) -> None: raise RuntimeError("throttled")
    assert await LambdaInvoker(Boom()).invoke("A", "fn", {}) == {"error": "throttled"}


async def test_mock_invoker_records() -> None:
    m = MockInvoker()
    res = await m.invoke("Reporter", "fn", {"job_id": "9"})
    assert res["mock"] and m.calls == [("Reporter", "fn", {"job_id": "9"})]


def test_settings_and_factory() -> None:
    s = load_settings({"MOCK_LAMBDAS": "TRUE", "REPORTER_FUNCTION": "r"})
    assert s.mock_lambdas and s.reporter_function == "r" and s.tagger_function.endswith("-tagger")
    assert isinstance(build_invoker(s), MockInvoker)


async def test_retry_succeeds_after_transient_failures() -> None:
    attempts = 0

    @with_retry(FAST, "t", logging.getLogger())
    async def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise AgentTemporaryError("throttled")
        return "done"

    assert await flaky() == "done" and attempts == 3


async def test_retry_gives_up_and_skips_non_retryable() -> None:
    calls = {"n": 0}

    @with_retry(FAST, "t", logging.getLogger())
    async def always() -> None:
        calls["n"] += 1
        raise TimeoutError()

    with pytest.raises(RetryError):
        await always()
    assert calls["n"] == 3

    @with_retry(FAST, "t", logging.getLogger())
    async def bad() -> None:
        calls["n"] += 100
        raise ValueError("x")

    with pytest.raises(ValueError):
        await bad()
    assert calls["n"] == 103


class H(BaseLambdaHandler):
    def validate(self, event) -> None:
        if "job_id" not in event: raise BadRequestError("job_id is required")
    def process(self, event):
        if event["job_id"] == "boom": raise RuntimeError("bad")
        return {"job": event["job_id"]}


def test_handler_status_codes() -> None:
    h = H()
    assert h({"job_id": "1"})["statusCode"] == 200
    assert h(json.dumps({"job_id": "1"}))["statusCode"] == 200
    assert h({})["statusCode"] == 400
    assert h({"job_id": "boom"})["statusCode"] == 500
