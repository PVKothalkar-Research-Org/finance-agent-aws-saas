"""Typed portfolio domain models and pure calculations shared by all agents.

Rows from the Data API arrive as loosely-typed dicts (numerics as strings,
JSON columns as dicts). ``from_row`` constructors are the single place where
that is converted into validated types.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

Row = Mapping[str, Any]


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    return float(value)


class AssetAllocation(BaseModel):
    """Percentage (0-100) breakdown keyed by label (asset class, region or sector)."""

    weights: dict[str, float] = Field(default_factory=dict)

    @field_validator("weights", mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> dict[str, float]:
        return {str(k): float(v) for k, v in (value or {}).items()}

    def pct(self, key: str) -> float:
        return self.weights.get(key, 0.0)


class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str = ""
    instrument_type: str = ""
    current_price: float | None = None
    asset_class: AssetAllocation = Field(default_factory=AssetAllocation)
    regions: AssetAllocation = Field(default_factory=AssetAllocation)
    sectors: AssetAllocation = Field(default_factory=AssetAllocation)

    @property
    def has_allocations(self) -> bool:
        return bool(self.asset_class.weights and self.regions.weights and self.sectors.weights)

    def price_or(self, default: float) -> float:
        return default if self.current_price is None else self.current_price

    @classmethod
    def from_row(cls, row: Row) -> Instrument:
        price = row.get("current_price")
        return cls(
            symbol=row["symbol"],
            name=row.get("name") or "",
            instrument_type=row.get("instrument_type") or "",
            current_price=None if price in (None, "") else float(price),
            asset_class=AssetAllocation(weights=row.get("allocation_asset_class") or {}),
            regions=AssetAllocation(weights=row.get("allocation_regions") or {}),
            sectors=AssetAllocation(weights=row.get("allocation_sectors") or {}),
        )


class Position(BaseModel):
    symbol: str
    quantity: float = 0.0
    instrument: Instrument | None = None

    def value(self, default_price: float | None = None) -> float:
        """Market value. With no price and no ``default_price`` the position counts as 0."""
        price = self.instrument.current_price if self.instrument else None
        if price is None:
            price = default_price
        return 0.0 if price is None else self.quantity * price


class Account(BaseModel):
    id: str = ""
    name: str = "Unknown"
    type: str = "investment"
    cash_balance: float = 0.0
    positions: list[Position] = Field(default_factory=list)

    @classmethod
    def from_row(cls, row: Row, positions: list[Position]) -> Account:
        return cls(
            id=str(row["id"]),
            name=row.get("account_name") or "Unknown",
            type=row.get("account_type") or "investment",
            cash_balance=_to_float(row.get("cash_balance")),
            positions=positions,
        )


class UserProfile(BaseModel):
    years_until_retirement: int = 30
    target_retirement_income: float = 80_000.0
    current_age: int = 40

    @classmethod
    def from_row(cls, row: Row | None) -> UserProfile:
        if not row:
            return cls()
        defaults = cls()
        years = row.get("years_until_retirement")
        income = row.get("target_retirement_income")
        return cls(
            years_until_retirement=defaults.years_until_retirement if years is None else int(years),
            target_retirement_income=defaults.target_retirement_income if income is None else float(income),
        )


class Portfolio(BaseModel):
    user_id: str = ""
    job_id: str = ""
    user: UserProfile = Field(default_factory=UserProfile)
    accounts: list[Account] = Field(default_factory=list)

    @property
    def cash_balance(self) -> float:
        return sum(a.cash_balance for a in self.accounts)

    @property
    def num_positions(self) -> int:
        return sum(len(a.positions) for a in self.accounts)

    @property
    def unique_symbols(self) -> set[str]:
        return {p.symbol for a in self.accounts for p in a.positions if p.symbol}

    def total_value(self, default_price: float | None = None) -> float:
        """Cash plus position values (see :meth:`Position.value` for pricing rules)."""
        return self.cash_balance + sum(p.value(default_price) for a in self.accounts for p in a.positions)

    @classmethod
    def from_event(cls, data: Mapping[str, Any]) -> Portfolio:
        """Parse the legacy ``portfolio_data`` dict that callers may pass in the event."""
        accounts = []
        for acc in data.get("accounts", []):
            positions = []
            for pos in acc.get("positions", []):
                symbol = pos.get("symbol") or ""
                inst = pos.get("instrument")
                positions.append(
                    Position(
                        symbol=symbol,
                        quantity=_to_float(pos.get("quantity")),
                        instrument=Instrument.from_row({"symbol": symbol, **inst}) if inst else None,
                    )
                )
            accounts.append(
                Account(
                    id=str(acc.get("id", "")),
                    name=acc.get("name") or "Unknown",
                    type=acc.get("type") or "investment",
                    cash_balance=_to_float(acc.get("cash_balance")),
                    positions=positions,
                )
            )
        return cls(
            user_id=data.get("user_id", ""),
            job_id=data.get("job_id", ""),
            user=UserProfile(years_until_retirement=int(data.get("years_until_retirement", 30))),
            accounts=accounts,
        )


class PortfolioDb(Protocol):
    """The slice of the Database facade the loader needs (eases test doubles)."""

    jobs: Any
    users: Any
    accounts: Any
    positions: Any
    instruments: Any


class JobNotFoundError(LookupError):
    """Raised when a job id has no matching row."""


def load_portfolio(db: PortfolioDb, job_id: str) -> Portfolio:
    """Load a job's user, accounts, positions and instruments into a Portfolio."""
    job = db.jobs.find_by_id(job_id)
    if not job:
        raise JobNotFoundError(f"Job {job_id} not found")
    user_id = job["clerk_user_id"]
    user_row = db.users.find_by_clerk_id(user_id)

    accounts: list[Account] = []
    for acc_row in db.accounts.find_by_user(user_id):
        positions: list[Position] = []
        for pos_row in db.positions.find_by_account(acc_row["id"]):
            inst_row = db.instruments.find_by_symbol(pos_row["symbol"])
            if inst_row:
                positions.append(
                    Position(
                        symbol=pos_row["symbol"],
                        quantity=_to_float(pos_row.get("quantity")),
                        instrument=Instrument.from_row(inst_row),
                    )
                )
        accounts.append(Account.from_row(acc_row, positions))

    return Portfolio(
        user_id=user_id,
        job_id=job_id,
        user=UserProfile.from_row(user_row),
        accounts=accounts,
    )
