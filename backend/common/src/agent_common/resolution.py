"""Resolve a portfolio from the Lambda event or, failing that, from the database."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .handler import BadRequestError
from .portfolio import JobNotFoundError, Portfolio, PortfolioDb, load_portfolio

logger = logging.getLogger(__name__)


def resolve_portfolio(db: PortfolioDb, event: Mapping[str, Any], job_id: str) -> Portfolio:
    """``portfolio_data`` in the event wins; otherwise load by job id.

    Raises :class:`JobNotFoundError` (-> 404) or :class:`BadRequestError` (-> 400).
    """
    if event.get("portfolio_data"):
        return Portfolio.from_event(event["portfolio_data"])
    try:
        return load_portfolio(db, job_id)
    except JobNotFoundError:
        raise
    except Exception as exc:
        logger.error("Could not load portfolio from database: %s", exc)
        raise BadRequestError("No portfolio data provided") from exc
