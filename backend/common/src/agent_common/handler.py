"""Template-method base for Lambda handlers: parsing, validation, observability, error mapping."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

LambdaResponse = dict[str, Any]


class BadRequestError(ValueError):
    """Raised by ``validate`` to produce an HTTP 400 response."""


def response(status: int, body: Any) -> LambdaResponse:
    return {"statusCode": status, "body": json.dumps(body)}


def parse_event(event: Any) -> dict[str, Any]:
    """Events may arrive as JSON strings (direct invoke) or dicts."""
    return json.loads(event) if isinstance(event, str) else event


class BaseLambdaHandler(ABC):
    """Subclasses implement ``process``; the base owns the response envelope."""

    def __init__(self, observe: Any = None) -> None:
        self._observe = observe

    def validate(self, event: dict[str, Any]) -> None:  # noqa: B027 - optional hook
        """Raise :class:`BadRequestError` for invalid input."""

    @abstractmethod
    def process(self, event: dict[str, Any]) -> Any:
        """Do the work; the return value becomes the 200 body."""

    def __call__(self, event: Any, context: Any = None) -> LambdaResponse:
        try:
            parsed = parse_event(event)
            self.validate(parsed)
            if self._observe is not None:
                with self._observe():
                    result = self.process(parsed)
            else:
                result = self.process(parsed)
            return response(200, result)
        except BadRequestError as exc:
            return response(400, {"error": str(exc)})
        except Exception as exc:
            logger.exception("Lambda handler error")
            return response(500, {"error": str(exc)})
