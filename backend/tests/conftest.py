"""Shared fixtures. Agent folders are added to sys.path so their *pure* modules
(simulation, orchestration, metrics, analysis) import under unique names."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

BACKEND = Path(__file__).resolve().parent.parent
for agent in ("planner", "retirement", "reporter", "charter"):
    sys.path.insert(0, str(BACKEND / agent))
sys.path.insert(0, str(BACKEND / "database"))


def load_module(name: str, path: Path) -> ModuleType:
    """Import a file under a unique name (agent.py exists in several agent folders)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeRepo:
    """Callable-attribute repository stub: FakeRepo(find_by_id=lambda x: ...)."""

    def __init__(self, **methods):
        self.__dict__.update(methods)


class FakeDb:
    """In-memory stand-in for the Database facade used by loaders and the planner."""

    def __init__(self, *, job=True, positions=None, instruments=None, accounts=None, user=None):
        self.job = {"id": "job-1", "clerk_user_id": "user-1"} if job else None
        self.user = user if user is not None else {"years_until_retirement": 20, "target_retirement_income": "70000"}
        self._accounts = accounts if accounts is not None else [{"id": "a1", "account_name": "IRA", "cash_balance": "50"}]
        self._positions = positions if positions is not None else [{"symbol": "VTI", "quantity": "2"}]
        self._instruments = instruments if instruments is not None else {
            "VTI": {"symbol": "VTI", "name": "Total Market", "current_price": "10",
                    "allocation_asset_class": {"equity": 100}, "allocation_regions": {"north_america": 100},
                    "allocation_sectors": {"technology": 100}}}
        self.jobs = FakeRepo(find_by_id=lambda _id: self.job)
        self.users = FakeRepo(find_by_clerk_id=lambda _id: self.user)
        self.accounts = FakeRepo(find_by_user=lambda _id: self._accounts)
        self.positions = FakeRepo(find_by_account=lambda _id: self._positions)
        self.instruments = FakeRepo(find_by_symbol=lambda s: self._instruments.get(s))


@pytest.fixture
def fake_db() -> type[FakeDb]:
    return FakeDb


def pytest_collection_modifyitems(config, items):
    import os

    if os.environ.get("RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="integration test: set RUN_INTEGRATION=1 with AWS credentials")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
