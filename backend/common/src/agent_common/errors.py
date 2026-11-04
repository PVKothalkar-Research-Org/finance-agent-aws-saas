"""Shared exception types."""


class AgentTemporaryError(Exception):
    """A transient failure (throttling, timeout) that should trigger a retry."""


TEMPORARY_MARKERS = ("timeout", "throttled")


def classify_agent_error(exc: BaseException) -> BaseException:
    """Map an arbitrary agent-run exception to a retryable or non-retryable one.

    Timeouts and throttling messages become :class:`AgentTemporaryError`
    (so the retry policy picks them up); anything else is returned unchanged.
    """
    if isinstance(exc, AgentTemporaryError):
        return exc
    if isinstance(exc, TimeoutError):
        return AgentTemporaryError(f"Timeout during agent execution: {exc}")
    text = str(exc).lower()
    if any(marker in text for marker in TEMPORARY_MARKERS):
        return AgentTemporaryError(f"Temporary error: {exc}")
    return exc
