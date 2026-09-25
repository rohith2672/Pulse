import pytest

from producer import generate_order_event
from validation import REQUIRED_STRING_FIELDS, validate_order


def valid_order(**overrides):
    order = {
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "order_id": "ord_a3f9b12c84",
        "user_id": "usr_f3a1b2c4",
        "product_id": "prd_9d8e7f6a",
        "category": "electronics",
        "price": 149.99,
        "quantity": 2,
        "city": "New York",
        "event_timestamp": "2026-03-11T10:23:45.123456Z",
    }
    order.update(overrides)
    return order


def test_valid_order_has_no_errors():
    assert validate_order(valid_order()) == []


def test_producer_output_always_passes_validation():
    for _ in range(200):
        assert validate_order(generate_order_event()) == []


@pytest.mark.parametrize("order", [None, {}, {k: None for k in valid_order()}])
def test_malformed_input(order):
    assert validate_order(order) == ["malformed_json"]


@pytest.mark.parametrize("field", REQUIRED_STRING_FIELDS)
@pytest.mark.parametrize("bad_value", [None, "", "   "])
def test_missing_required_field(field, bad_value):
    assert validate_order(valid_order(**{field: bad_value})) == [f"missing_{field}"]


def test_missing_price_and_quantity():
    errors = validate_order(valid_order(price=None, quantity=None))
    assert errors == ["missing_price", "missing_quantity"]


@pytest.mark.parametrize("price", [0, -5.0, "12.50", True])
def test_invalid_price(price):
    assert validate_order(valid_order(price=price)) == ["invalid_price"]


@pytest.mark.parametrize("quantity", [0, -1, 1.5, "2", True])
def test_invalid_quantity(quantity):
    assert validate_order(valid_order(quantity=quantity)) == ["invalid_quantity"]


@pytest.mark.parametrize("ts", ["not-a-date", "2026-13-45T00:00:00Z", "11/03/2026"])
def test_invalid_event_timestamp(ts):
    assert validate_order(valid_order(event_timestamp=ts)) == ["invalid_event_timestamp"]


def test_multiple_errors_are_all_reported():
    errors = validate_order(valid_order(order_id=None, price=-1, quantity=0))
    assert errors == ["missing_order_id", "invalid_price", "invalid_quantity"]
