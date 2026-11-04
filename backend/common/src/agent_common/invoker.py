"""Injectable agent invocation: real Lambda, or a mock for local runs and tests."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

from .settings import Settings

logger = logging.getLogger(__name__)

type InvocationResult = dict[str, Any]


class AgentInvoker(Protocol):
    """Anything that can run a named agent with a JSON payload."""

    async def invoke(self, agent_name: str, function_name: str, payload: dict[str, Any]) -> InvocationResult: ...


def unwrap_lambda_response(result: Any) -> Any:
    """Unwrap the ``{statusCode, body}`` envelope returned by Lambda handlers."""
    if isinstance(result, dict) and "statusCode" in result and "body" in result:
        body = result["body"]
        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"message": body}
        return body
    return result


class LambdaInvoker:
    """Invoke agents as AWS Lambda functions (synchronous RequestResponse)."""

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            import boto3

            client = boto3.client("lambda")
        self._client = client

    async def invoke(self, agent_name: str, function_name: str, payload: dict[str, Any]) -> InvocationResult:
        try:
            logger.info("Invoking %s Lambda: %s", agent_name, function_name)
            # boto3 is blocking: run it in a thread so parallel tool calls really overlap.
            response = await asyncio.to_thread(
                self._client.invoke,
                FunctionName=function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload),
            )
            result = unwrap_lambda_response(json.loads(response["Payload"].read()))
            logger.info("%s completed successfully", agent_name)
            return result
        except Exception as exc:  # noqa: BLE001 - surfaced to the LLM as an error string
            logger.error("Error invoking %s: %s", agent_name, exc)
            return {"error": str(exc)}


class MockInvoker:
    """Records calls and returns a canned success; used locally and in tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def invoke(self, agent_name: str, function_name: str, payload: dict[str, Any]) -> InvocationResult:
        self.calls.append((agent_name, function_name, payload))
        logger.info("[MOCK] Would invoke %s with payload: %s", agent_name, json.dumps(payload)[:200])
        return {"success": True, "message": f"[Mock] {agent_name} completed", "mock": True}


def build_invoker(settings: Settings) -> AgentInvoker:
    """Composition-root helper: the only place the mock flag is consulted."""
    return MockInvoker() if settings.mock_lambdas else LambdaInvoker()
