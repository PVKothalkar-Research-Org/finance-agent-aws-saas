"""Typed shapes of the dict rows returned by the Data API client.

Numerics (``quantity``, ``current_price``, ``cash_balance``...) arrive as strings
from the Data API and JSON columns arrive already parsed.
"""

from __future__ import annotations

from typing import Any, TypedDict


class UserRow(TypedDict, total=False):
    clerk_user_id: str
    display_name: str | None
    years_until_retirement: int | None
    target_retirement_income: Any  # numeric string
    asset_class_targets: dict[str, float]
    region_targets: dict[str, float]
    created_at: str
    updated_at: str


class InstrumentRow(TypedDict, total=False):
    symbol: str
    name: str
    instrument_type: str
    current_price: Any  # numeric string or None
    allocation_regions: dict[str, float]
    allocation_sectors: dict[str, float]
    allocation_asset_class: dict[str, float]


class AccountRow(TypedDict, total=False):
    id: str
    clerk_user_id: str
    account_name: str
    account_purpose: str | None
    cash_balance: Any
    cash_interest: Any
    created_at: str


class PositionRow(TypedDict, total=False):
    id: str
    account_id: str
    symbol: str
    quantity: Any
    as_of_date: str
    instrument_name: str  # joined from instruments
    instrument_type: str  # joined from instruments
    current_price: Any  # joined from instruments


class JobRow(TypedDict, total=False):
    id: str
    clerk_user_id: str
    job_type: str
    status: str
    request_payload: dict[str, Any] | None
    report_payload: dict[str, Any] | None
    charts_payload: dict[str, Any] | None
    retirement_payload: dict[str, Any] | None
    summary_payload: dict[str, Any] | None
    error_message: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


class PortfolioValue(TypedDict):
    num_positions: int
    total_value: float
    total_shares: float
