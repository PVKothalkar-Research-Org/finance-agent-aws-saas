"""Pure charter logic: portfolio breakdown text and chart-JSON parsing."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from agent_common import Portfolio

logger = logging.getLogger()

DEFAULT_PRICE = 1.0  # legacy behaviour: unpriced instruments valued at $1
TOP_HOLDINGS = 10
TOP_SECTORS = 10


def _sorted_desc(values: dict[str, float], limit: int | None = None) -> list[tuple[str, float]]:
    ranked = sorted(values.items(), key=lambda kv: kv[1], reverse=True)
    return ranked if limit is None else ranked[:limit]


def analyze_portfolio(portfolio: Portfolio) -> str:
    """Detailed breakdown of accounts, top holdings and aggregated allocations."""
    total_value = 0.0
    position_values: dict[str, float] = defaultdict(float)
    account_totals: dict[str, dict[str, Any]] = {}

    for account in portfolio.accounts:
        entry = account_totals.setdefault(account.name, {"value": 0.0, "type": account.type})
        entry["value"] += account.cash_balance
        total_value += account.cash_balance
        for position in account.positions:
            if position.instrument is None or position.instrument.current_price is None:
                logger.warning("Charter: No price for %s, using default of %s", position.symbol, DEFAULT_PRICE)
            value = position.value(default_price=DEFAULT_PRICE)
            position_values[position.symbol] += value
            entry["value"] += value
            total_value += value

    lines = [
        "Portfolio Analysis:",
        f"Total Value: ${total_value:,.2f}",
        f"Number of Accounts: {len(account_totals)}",
        f"Number of Positions: {len(position_values)}",
        "\nAccount Breakdown:",
    ]
    for name, data in account_totals.items():
        pct = data["value"] / total_value * 100 if total_value > 0 else 0
        lines.append(f"  {name} ({data['type']}): ${data['value']:,.2f} ({pct:.1f}%)")

    lines.append("\nTop Holdings by Value:")
    for symbol, value in _sorted_desc(position_values, TOP_HOLDINGS):
        pct = value / total_value * 100 if total_value > 0 else 0
        lines.append(f"  {symbol}: ${value:,.2f} ({pct:.1f}%)")

    asset_classes: dict[str, float] = defaultdict(float)
    regions: dict[str, float] = defaultdict(float)
    sectors: dict[str, float] = defaultdict(float)
    for account in portfolio.accounts:
        for position in account.positions:
            value = position.value(default_price=DEFAULT_PRICE)
            if position.instrument is None:
                continue
            for label, pct in position.instrument.asset_class.weights.items():
                asset_classes[label] += value * pct / 100
            for label, pct in position.instrument.regions.weights.items():
                regions[label] += value * pct / 100
            for label, pct in position.instrument.sectors.weights.items():
                sectors[label] += value * pct / 100

    if portfolio.cash_balance > 0:
        asset_classes["cash"] += portfolio.cash_balance

    lines.append("\nCalculated Allocations:")
    lines.append("\nAsset Classes:")
    lines += [f"  {k}: ${v:,.2f}" for k, v in _sorted_desc(asset_classes)]
    lines.append("\nGeographic Regions:")
    lines += [f"  {k}: ${v:,.2f}" for k, v in _sorted_desc(regions)]
    lines.append("\nSectors:")
    lines += [f"  {k}: ${v:,.2f}" for k, v in _sorted_desc(sectors, TOP_SECTORS)]
    return "\n".join(lines)


def extract_charts(output: str | None) -> dict[str, dict[str, Any]]:
    """Parse the model's JSON (``{"charts": [...]}``) into ``{chart_key: chart}``.

    Returns an empty dict when no valid JSON/charts are found.
    """
    if not output:
        return {}
    start, end = output.find("{"), output.rfind("}")
    if start < 0 or end <= start:
        logger.error("Charter: No JSON structure found in output")
        return {}
    try:
        parsed = json.loads(output[start : end + 1])
    except json.JSONDecodeError as exc:
        logger.error("Charter: Failed to parse JSON: %s", exc)
        return {}

    charts: dict[str, dict[str, Any]] = {}
    for chart in parsed.get("charts", []):
        key = chart.get("key", f"chart_{len(charts) + 1}")
        charts[key] = {k: v for k, v in chart.items() if k != "key"}
    return charts
