from datetime import datetime

import pytest

from producer import CATEGORIES, current_utc_iso, generate_order_event

EXPECTED_KEYS = {
    "event_id",
    "order_id",
    "user_id",
    "product_id",
    "category",
    "price",
    "quantity",
    "city",
    "event_timestamp",
}


@pytest.fixture
def events():
    return [generate_order_event() for _ in range(200)]


def test_event_has_exactly_the_expected_keys(events):
    for event in events:
        assert set(event) == EXPECTED_KEYS


def test_price_and_quantity_ranges(events):
    for event in events:
        assert 10.0 <= event["price"] <= 500.0
        assert round(event["price"], 2) == event["price"]
        assert isinstance(event["quantity"], int)
        assert 1 <= event["quantity"] <= 5


def test_category_is_from_allowed_list(events):
    for event in events:
        assert event["category"] in CATEGORIES


def test_id_prefixes(events):
    for event in events:
        assert event["order_id"].startswith("ord_")
        assert event["user_id"].startswith("usr_")
        assert event["product_id"].startswith("prd_")


def test_event_ids_are_unique(events):
    assert len({e["event_id"] for e in events}) == len(events)


def test_current_utc_iso_is_zulu_and_parseable():
    ts = current_utc_iso()
    assert ts.endswith("Z")
    parsed = datetime.fromisoformat(ts[:-1] + "+00:00")
    assert parsed.utcoffset().total_seconds() == 0
