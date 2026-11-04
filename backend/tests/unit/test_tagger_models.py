import sys
from decimal import Decimal

import pytest

pytest.importorskip("litellm")
pytest.importorskip("agents")
from pydantic import ValidationError

from tests.conftest import BACKEND, load_module


@pytest.fixture(scope="module")
def tagger():
    saved = {k: sys.modules.pop(k) for k in ("templates",) if k in sys.modules}
    sys.path.insert(0, str(BACKEND / "tagger"))
    try:
        yield load_module("tagger_agent", BACKEND / "tagger" / "agent.py")
    finally:
        sys.path.remove(str(BACKEND / "tagger"))
        sys.modules.pop("templates", None)
        sys.modules.update(saved)


def make(tagger, **overrides):
    base = dict(
        symbol="VTI", name="Vanguard Total Stock Market ETF", instrument_type="etf", current_price=250.5,
        allocation_asset_class={"equity": 100},
        allocation_regions={"north_america": 95, "international": 5},
        allocation_sectors={"technology": 30, "financials": 20, "other": 50},
    )
    base.update(overrides)
    return tagger.InstrumentClassification(**base)


def test_valid_classification_round_trips_to_db_format(tagger):
    db = tagger.classification_to_db_format(make(tagger))
    assert db.symbol == "VTI" and db.current_price == Decimal("250.5")
    assert db.allocation_asset_class == {"equity": 100}
    assert db.allocation_regions == {"north_america": 95, "international": 5}
    assert set(db.allocation_sectors) == {"technology", "financials", "other"}


def test_global_alias_maps_to_global_key(tagger):
    c = make(tagger, allocation_regions={"global": 100})
    assert tagger.classification_to_db_format(c).allocation_regions == {"global": 100}


@pytest.mark.parametrize("field,value", [
    ("allocation_asset_class", {"equity": 60}),
    ("allocation_regions", {"europe": 50, "asia": 10}),
    ("allocation_sectors", {"technology": 90, "other": 20}),
])
def test_allocations_must_sum_to_about_100(tagger, field, value):
    with pytest.raises(ValidationError, match="sum to 100"):
        make(tagger, **{field: value})


def test_sum_tolerance_is_three_points(tagger):
    make(tagger, allocation_asset_class={"equity": 97.5})
    with pytest.raises(ValidationError):
        make(tagger, allocation_asset_class={"equity": 96})


def test_price_must_be_positive_and_unknown_fields_rejected(tagger):
    with pytest.raises(ValidationError):
        make(tagger, current_price=0)
    with pytest.raises(ValidationError):
        make(tagger, surprise="x")
