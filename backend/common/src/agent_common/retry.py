"""Retry policy object wrapping tenacity so every agent retries the same way."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import ParamSpec, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .errors import AgentTemporaryError

P = ParamSpec("P")
R = TypeVar("R")

DEFAULT_RETRYABLE: tuple[type[BaseException], ...] = (
    AgentTemporaryError,
    TimeoutError,
    asyncio.TimeoutError,
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential-backoff policy. ``wait_min``/``wait_max`` are seconds."""

    max_attempts: int = 5
    wait_multiplier: float = 1.0
    wait_min: float = 4.0
    wait_max: float = 60.0
    retryable: tuple[type[BaseException], ...] = DEFAULT_RETRYABLE

    def extended(self, *extra: type[BaseException]) -> RetryPolicy:
        """Return a copy that also retries on ``extra`` exception types."""
        return RetryPolicy(
            self.max_attempts, self.wait_multiplier, self.wait_min, self.wait_max,
            tuple(dict.fromkeys(self.retryable + extra)),
        )


def with_retry(
    policy: RetryPolicy, name: str, logger: logging.Logger
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator factory applying ``policy`` to an async function."""

    def log_before_sleep(state) -> None:  # tenacity RetryCallState
        logger.info("%s: temporary error, retrying in %s seconds...", name, state.next_action.sleep)

    return retry(
        retry=retry_if_exception_type(policy.retryable),
        stop=stop_after_attempt(policy.max_attempts),
        wait=wait_exponential(multiplier=policy.wait_multiplier, min=policy.wait_min, max=policy.wait_max),
        before_sleep=log_before_sleep,
        reraise=False,
    )
