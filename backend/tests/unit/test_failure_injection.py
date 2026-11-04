"""Force throttling/timeouts in the agent run and prove the retry policy reacts correctly."""

import logging

import pytest
from agent_common import AgentTemporaryError, RetryPolicy, classify_agent_error, with_retry
from tenacity import RetryError

FAST = RetryPolicy(max_attempts=5, wait_multiplier=0, wait_min=0, wait_max=0)
log = logging.getLogger("test")


class FailureInjector:
    """Raises the given exceptions in order, then returns ``result``. Counts attempts."""

    def __init__(self, failures, result="ok"):
        self.failures, self.result, self.attempts = list(failures), result, 0

    async def run(self):
        self.attempts += 1
        if self.failures:
            raise self.failures.pop(0)
        return self.result


def make_runner(injector, policy=FAST):
    """Mimics run_*_agent: run the agent, map errors, retry via the shared policy."""

    @with_retry(policy, "Agent", log)
    async def run_agent():
        try:
            return await injector.run()
        except Exception as exc:
            mapped = classify_agent_error(exc)
            if isinstance(mapped, AgentTemporaryError):
                raise mapped from exc
            raise

    return run_agent


@pytest.mark.parametrize("failure", [
    TimeoutError("socket timeout"),
    TimeoutError(),
    RuntimeError("ThrottlingException: Too many requests, request throttled"),
    RuntimeError("Read TIMEOUT on endpoint"),
])
async def test_transient_failures_are_retried_until_success(failure):
    inj = FailureInjector([failure, failure])
    assert await make_runner(inj)() == "ok"
    assert inj.attempts == 3


async def test_retries_stop_after_max_attempts():
    inj = FailureInjector([TimeoutError("t")] * 10)
    with pytest.raises(RetryError):
        await make_runner(inj)()
    assert inj.attempts == FAST.max_attempts


async def test_non_retryable_error_fails_immediately():
    inj = FailureInjector([ValueError("bad input")])
    with pytest.raises(ValueError, match="bad input"):
        await make_runner(inj)()
    assert inj.attempts == 1


async def test_policy_extension_adds_custom_retryable_type():
    class RateLimit(Exception):
        pass

    policy = FAST.extended(RateLimit)
    inj = FailureInjector([RateLimit(), RateLimit()])

    @with_retry(policy, "Agent", log)
    async def run():
        return await inj.run()

    assert await run() == "ok" and inj.attempts == 3
    # the base policy does NOT retry it
    inj2 = FailureInjector([RateLimit()])

    @with_retry(FAST, "Agent", log)
    async def run2():
        return await inj2.run()

    with pytest.raises(RateLimit):
        await run2()
    assert inj2.attempts == 1


def test_classify_agent_error_mapping():
    assert isinstance(classify_agent_error(TimeoutError("x")), AgentTemporaryError)
    assert isinstance(classify_agent_error(RuntimeError("was Throttled")), AgentTemporaryError)
    plain = ValueError("nope")
    assert classify_agent_error(plain) is plain
