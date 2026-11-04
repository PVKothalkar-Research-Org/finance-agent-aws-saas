"""Pure reporter logic: portfolio metrics and the analysis prompt text."""

from __future__ import annotations

from dataclasses import dataclass

from agent_common import Instrument, Portfolio, UserProfile

TOP_REGIONS = 2


@dataclass(frozen=True, slots=True)
class PortfolioMetrics:
    total_value: float
    cash_balance: float
    num_accounts: int
    num_positions: int
    unique_symbols: int


def calculate_portfolio_metrics(portfolio: Portfolio) -> PortfolioMetrics:
    """Totals use priced positions only (unpriced positions contribute 0), plus cash."""
    return PortfolioMetrics(
        total_value=portfolio.total_value(),
        cash_balance=portfolio.cash_balance,
        num_accounts=len(portfolio.accounts),
        num_positions=portfolio.num_positions,
        unique_symbols=len(portfolio.unique_symbols),
    )


def describe_allocations(instrument: Instrument | None) -> str:
    """`` (Asset: equity 100%, Regions: north_america 60%, europe 20%)`` or empty string."""
    if instrument is None:
        return ""
    parts: list[str] = []
    if instrument.asset_class.weights:
        top = max(instrument.asset_class.weights, key=instrument.asset_class.weights.__getitem__)
        parts.append(f"Asset: {top}")
    if instrument.regions.weights:
        ranked = sorted(instrument.regions.weights.items(), key=lambda kv: kv[1], reverse=True)[:TOP_REGIONS]
        parts.append("Regions: " + ", ".join(f"{name} {pct:g}%" for name, pct in ranked))
    return f" ({', '.join(parts)})" if parts else ""


def format_portfolio_for_analysis(portfolio: Portfolio, user: UserProfile) -> str:
    m = calculate_portfolio_metrics(portfolio)
    lines = [
        "Portfolio Overview:",
        f"- {m.num_accounts} accounts",
        f"- {m.num_positions} total positions",
        f"- {m.unique_symbols} unique holdings",
        f"- ${m.cash_balance:,.2f} in cash",
        f"- ${m.total_value:,.2f} total value" if m.total_value > 0 else "",
        "",
        "Account Details:",
    ]
    for account in portfolio.accounts:
        lines.append(f"\n{account.name} (${account.cash_balance:,.2f} cash):")
        for position in account.positions:
            lines.append(
                f"  - {position.symbol}: {position.quantity:,.2f} shares{describe_allocations(position.instrument)}"
            )
    lines.extend(
        [
            "",
            "User Profile:",
            f"- Years to retirement: {user.years_until_retirement}",
            f"- Target retirement income: ${user.target_retirement_income:,.0f}/year",
        ]
    )
    return "\n".join(lines)
